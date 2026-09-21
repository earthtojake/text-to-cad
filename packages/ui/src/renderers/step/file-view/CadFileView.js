import { attachCadLiveBinding } from "../live.js";
import { normalizeOrbit } from "../../kit/tools/fullscreen/orbitPreferences.js";
import { buildEdgeChainGraph } from "../workbench/edgeChainSelection.js";
"use client";

import SelectionFilterMenu from "../components/workbench/SelectionFilterMenu.jsx";
import { stepGeometryContextText, stepGeometryPromptText } from "../workbench/stepGeometryPrompt.js";
import { filterSelectionReferences, toggleReferenceGroupSelection, connectedReferenceIds } from "../workbench/selectionFilter.js";
import { buildTangentFaceGraph } from "../workbench/tangentFaceSelection.js";

import * as THREE from "three";
import { startTransition, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { Camera, FileText } from "lucide-react";
import { CAD_PANEL, EmptyState } from "@hardcore/ui/navigation";
import { cn } from "@hardcore/ui/utils";
import StepViewport from "../scene/StepViewport.jsx";
import { viewportMenuEntries } from "../components/workbench/AssemblyContextMenuItems.js";
import { useViewportLod } from "../render/useViewportLod.js";
import { lodSceneMayMove } from "../render/lodCameraSample.js";
import { registerLodDisplaySource } from "../render/lodSceneAdoption.js";
import { buildDisplaySettingsTab } from "../../kit/view-settings/DisplaySettingsTab.js";
import { ALL_VIEW_FEATURES, EDGELESS_VIEW_FEATURES } from "@hardcore/core/common/viewSettings.js";
import { explodablePartCount } from "../workbench/explodableParts.js";
import { prefetchRenderStudio } from "../../kit/look/renderStudioChunk.js";
import StepFileSheet from "../components/workbench/StepFileSheet.js";
import { FileSheetPortalContext, HostPanelSlotContext } from "../../kit/inspector/FileSheet.js";
import { restoreMotionAnimation, restoreMotionParameters } from "../workbench/motionRestore.js";
import { useStepMotionControls } from "../workbench/useStepMotionControls.js";
import StatusToast from "../../kit/status/StatusToast.js";
import ViewerAlertDialog from "../../kit/status/ViewerAlertDialog.js";
import ViewerLoadingOverlay from "../../kit/status/ViewerLoadingOverlay.js";
import {
  ARTIFACT_PROGRESS_POLL_MS
} from "../workbench/artifactProgress.js";
import FloatingToolBar from "../components/workbench/FloatingToolBar.js";
import FullscreenToolbar from "../components/workbench/FullscreenToolbar.jsx";
import { ViewportAnimationBar, animationControlsHaveContent } from "../components/workbench/AnimationControlsSection.js";
import { useCadAssets } from "../components/workbench/hooks/useCadAssets.js";
import { resolveDesktopPanelWidth } from "./fileViewState.js";
import { useEditingPreview } from "../components/workbench/hooks/useEditingPreview.js";
import { useViewportQualityStatus } from "../components/workbench/hooks/useViewportQualityStatus.js";
import { previewGeometryChanged } from "../workbench/editingPreview.js";
import { resolveFileStatus } from "../../kit/status/fileStatus.js";
import { useFileActivityReport } from "../../kit/status/useFileActivityReport.js";
import MeasurePanel from "../components/workbench/MeasurePanel.jsx";
import { useDrawingSession } from "../../../drawing/session.js";
import { CAD_DRAWING_DEFAULTS } from "../../kit/tools/draw/DrawingOverlay.jsx";
import { viewerLoadingState } from "../../kit/status/loadingState.js";
import { useCadWorkspaceSelection } from "../components/workbench/hooks/useCadWorkspaceSelection.js";
import { useCadWorkspaceSelectors } from "../components/workbench/hooks/useCadWorkspaceSelectors.js";
import { useCadWorkspaceShortcuts } from "../components/workbench/hooks/useCadWorkspaceShortcuts.js";
import {
  cameraForViewSettings, normalizeViewerDisplaySettings, viewerDisplaySettingsForCamera
} from "../../kit/view-settings/viewerDisplaySettings.js";
import { useAppliedViewSettings } from "../../kit/view-settings/useAppliedViewSettings.js";
import { ViewUpdateStatus } from "../../kit/status/ViewUpdateStatus.jsx";
import { useViewSettings } from "../../kit/view-settings/useViewSettings.js";
import {
  annotatePerspectiveSnapshot,
  clonePerspectiveSnapshot
} from "@hardcore/core/lib/perspective.js";
import {
  ASSET_STATUS,
  CAD_TOOL_MODES,
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
import {
  entrySourceFormat,
  fileSheetKindForEntry
} from "@hardcore/core/lib/fileFormats.js";
import {
  assetKindForRenderFormat,
  hasCapability,
  isArtifactManagedFormat,
  parameterSourceKind,
  renderCapabilities,
  renderFormatLabel,
  supportsTool,
  ASSET_KIND,
  PARAMETER_SOURCE
} from "@hardcore/core/lib/renderCapabilities.js";
import {
  buildViewerMeshAlert,
  buildViewerEditAlert
} from "../workbench/viewerAlerts.js";
import { fileStatusAlertKey, resolveFileStatusAlert } from "../../kit/status/loadAlerts.js";
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
  entryHasMesh,
  entryHasReferences,
  entryMeshAssetSignature,
  entryPoseUrl
} from "@hardcore/core/lib/entryAssets.js";
import {
  hasStepGlbByteCost,
  isLargeMeshData,
  isLargeStepGlbEntry
} from "@hardcore/core/lib/render/meshCost.js";
import { cloneTabSnapshot, createTabRecord, tabSnapshotEqual } from "../workbench/state.js";
import { createFileSessionSnapshot, normalizeFileSessionState } from "../workbench/fileSessionState.js";
import { shallowObjectValuesEqual } from "../workbench/valueUtils.js";
import {
  createRenderSessionState,
  renderCameraSnapshot
} from "../workbench/renderSessionState.js";
import {
  animationClipList,
  animationRenderFrame,
  buildDefaultAnimationState,
  findAnimationClip,
  shouldPublishAnimationFrame
} from "@hardcore/core/common/animationClock.js";
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
import { CAD_WORKSPACE_LAYOUT_MODE } from "../workbench/breakpoints.js";
import { cadFileParamForEntry, cadPathForEntry, fileKey, sidebarLabelForEntry } from "../workbench/entryPaths.js";
import { buildCadRefToken, isNativeCadSelector } from "@hardcore/core/lib/cadRefs.js";
import {
  stepModuleRequiresTopology,
  stepModuleTopologyOccurrenceIds
} from "../workbench/topologyCapabilities.js";
import { shortestUniquePathSuffixes } from "@hardcore/core/lib/filePathSuffix.js";
import { stepJointHandles, stepPosableDofs } from "../workbench/jointHandles.js";
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
  normalizeStepModuleParameterValues,
  resolveStepModuleFeatures
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
import { ViewerElementContext, useViewerHost, usePromptDestination } from "../../../host/context.js";
import { createCadPromptContext } from "./promptContext.js";
import { promptDeliveryMessage } from "../../kit/shell/promptContext.js";
import { HostReferenceContext, referenceLabel, referencesFromCopyText, resolveSelectorSelection } from "./hostReference.js";
import { applySourceAppearanceToMeshData, sourceAppearanceGeometry } from "@hardcore/core/common/sourceSidecar.js";
const EMPTY_MATERIAL_OVERRIDES = Object.freeze({});
function sourceAnimationForEntry(entry) { return (entry?.editingPreview ? entry.previewAnimation : entry?.sourceSidecar?.animation) || null; }
function sourceAnimationKeyForEntry(entry) { return sourceAnimationForEntry(entry) ? `${fileKey(entry)}:${entry?.animationHash || entry?.documentHash || entry?.hash || "animation"}` : ""; }
function scopedWorkspacePerspective(snapshot, modelKey, entry) {
 const normalized = clonePerspectiveSnapshot(snapshot);
 if (!normalized) return null;
 const sceneScaleMode = renderCapabilities(entrySourceFormat(entry)).sceneScale;
 return annotatePerspectiveSnapshot(normalized, { modelKey, sceneScaleMode, coordinateSystem: "cad-z-up-v1" });
}

import {
  ARTIFACT_GENERATING_LABEL,
  DEFAULT_LARGE_FILE_STATE,
  DESKTOP_TAB_TOOLS_MAX_WIDTH,
  DESKTOP_TAB_TOOLS_MIN_WIDTH,
  EMPTY_LIST,
  entryWithoutRenderAssets,
  normalizeLargeFileState,
  readViewerLayoutMode,
  readViewerViewportWidth
} from "./fileViewState.js";
import { sceneBackdropEdgeColor } from "../../kit/look/chromeBackdrop.js";
import { useChromeBackdropColor } from "../../kit/look/useChromeBackdropColor.js";
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
  return <AnimationClockProvider value={clock}><CadFileViewSurface {...props} /></AnimationClockProvider>;
}


function CadFileViewSurface({
  client, entry, serverInfo, renderSession: cadRenderSession, preferences, onPreferenceChange, onOpenFile, className = "",
  panelSlot, colorScheme = "light", selectReference, captureRequest, acknowledgeCommand, documentResource, slots, live,
  fullscreen = false, onExitFullscreen, onNavigationActionsChange,
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
  // What the viewport's menu is ABOUT while it is up (the part stays marked); the menu itself,
  // its gesture and its dismissal are the shell's (`kit/shell/ViewportContextMenu.jsx`). The ref
  // is how the press that asks for the menu's entries reads the descriptor it just resolved.
  const [viewerContextMenu, setViewerContextMenuState] = useState(null);
  const viewerContextMenuRef = useRef(null);
  const setViewerContextMenu = useCallback((next) => {
    viewerContextMenuRef.current = next;
    setViewerContextMenuState(next);
  }, []);
  const { display: displaySettings, scene: desiredScene, store: viewSettingsStore } = useViewSettings(resolvedColorSchemeMode);
  const viewerRef = useRef(null);
  const viewUpdate = useAppliedViewSettings(desiredScene, selectedKey, viewerRef, viewSettingsStore);
  const resolvedScene = viewUpdate.scene;
  const [renderSession, setRenderSession] = useState(createRenderSessionState);
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
  const rendering = resolvedScene.render.enabled;
  useEffect(() => { if (rendering) prefetchRenderStudio(); }, [rendering]);
  const resolvedThemeSettings = resolvedScene.theme;
  const resolvedMaterialOverrides = resolvedScene.materialOverrides || EMPTY_MATERIAL_OVERRIDES;
  const sceneBackdrop = useMemo(
    () => resolvedScene.view.background.enabled && resolvedScene.view.background.opacity === 1
      ? resolvedScene.view.background.color
      : resolvedScene.view.background.enabled ? chromeBackdropColor
        : sceneBackdropEdgeColor(resolvedThemeSettings?.background, chromeBackdropColor),
    [chromeBackdropColor, resolvedThemeSettings, resolvedScene.view.background]
  );
  const resolvedDisplayEdgeSettings = resolvedScene.display.edges;
  const previewMode = fullscreen;
  const previewOrbitSpeed = normalizeOrbit(preferences.orbit).speed;
  const setPreviewOrbitSpeed = useCallback(speed => onPreferenceChange({ orbit: normalizeOrbit({ speed }) }), [onPreferenceChange]);
  useEffect(() => { onChromeVisibilityChange?.(!previewMode); }, [onChromeVisibilityChange, previewMode]);
  const tabToolsWidth = 365;
  const [tabToolMode, setTabToolMode] = useState(TAB_TOOL_MODE.REFERENCES);
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
  const motionRevisionRef = useRef(0);
  const lastPersistenceFailureKeyRef = useRef("");
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
    cancelMeshLoad,
    cancelReferenceLoad,
    cancelDisplayEdgeLoad,
    loadMeshForEntry,
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
  // Every entry renders from its own source format: nothing is baked into a package
  // under a different one.
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
  const supportsParts = hasCapability(selectedEntrySourceFormat, "parts");
  const supportsTopology = hasCapability(selectedEntrySourceFormat, "topology");
  // What this file's view opts into: a B-rep model takes every Display section, preset and surface
  // style; every other format the set without edges, Clip or Explode.
  const viewFeatures = supportsTopology ? ALL_VIEW_FEATURES : EDGELESS_VIEW_FEATURES;
  useLayoutEffect(() => { viewSettingsStore.configure({ features: viewFeatures }); }, [viewSettingsStore, viewFeatures]);
  const supportsMeasure = hasCapability(selectedEntrySourceFormat, "measure");
  const supportsSidecarParams =
    parameterSourceKind(selectedEntrySourceFormat) === PARAMETER_SOURCE.SIDECAR;
  const isAssemblyView = selectedEntry?.kind === "assembly";
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
  const selectedEntryHasReferences = entryHasReferences(selectedEntry);
  const selectedEntryHasDisplayEdges = entryHasDisplayEdges(selectedEntry);
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
      stepModuleParameterValuesRef.current = {};
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
    stepModuleParameterValuesRef.current = {};
    setStepModuleParameterValues({});

    const loadMotionRevision = motionRevisionRef.current;
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
      const parameterValues = restoreMotionParameters(definition, resolved.parameterValues,
        motionRevisionRef.current === loadMotionRevision ? restoredSessionState?.slices?.animation : animationStateRef.current);
      stepModuleParameterValuesRef.current = parameterValues;
      setStepModuleParameterValues(parameterValues);
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
      stepModuleParameterValuesRef.current = {};
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

    const loadMotionRevision = motionRevisionRef.current;
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
        const nextState = restoreMotionAnimation(
          motionRevisionRef.current === loadMotionRevision ? restoredSessionState?.slices?.animation : animationStateRef.current, clips);
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

  const selectedMeshData = (selectedMeshMatches || retainingPreviousStepMesh) ? meshState.meshData : null;
  const selectedSourceAppearance = selectedEntry?.editingPreview
    ? selectedEntry.previewAppearance || null
    : selectedEntry?.sourceSidecar
      ? selectedEntry.sourceSidecar.appearance || null
      : selectedMeshData?.appearance || null;
  const selectedDisplayMeshData = useMemo(() => {
    return registerLodDisplaySource(
      applySourceAppearanceToMeshData(selectedMeshData, selectedSourceAppearance),
      selectedMeshData
    );
  }, [selectedMeshData, selectedSourceAppearance]);
  const handleDisplayMeshAdoption = useCallback((source, ok, detail) =>
    onMeshSourceAdoption(sourceAppearanceGeometry(source), ok, detail), [onMeshSourceAdoption]);
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
    selectedStepModuleTopologyRequired;
  // What the viewport needs to draw one animated frame: the compiled clip and a
  // time. The render pane swaps in the live clock while playing; everything else
  // about playback stays out of the render path.
  //
  // `enabled` is internal pose ownership: paused animation holds its frame;
  // editing Position hands control back to kinematics. It is not a UI gate.
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

  // The pose the person PICKED, which the dropdown shows until they move a DOF. Without
  // it the name is re-derived from the values every frame, so a pose read as "None"
  // for the whole of its own transition and only became itself once it arrived.
  const [appliedStepPoseName, setAppliedStepPoseName] = useState("");

  // A named pose is a full configuration, not a patch: every DOF the preset
  // does not mention returns to 0 (the artifact as written), so two presets in
  // a row can never leave a joint behind from the first.
  const {
    handleStepModuleParameterChange, applyStepModuleParameterValues, handleResetStepModuleParameters,
    handleApplyPose, handleAnimationClipSelect, handleAnimationPlayToggle, handleAnimationRestart,
    handleAnimationScrub, handleAnimationSpeedChange, handleAnimationLoopToggle, resetMotion: resetStepMotion,
    releaseAnimation: releaseStepAnimation
  } = useStepMotionControls({
    selectedStepModuleDefinition, selectedAnimationClips, selectedActiveAnimationClip,
    animationState, animationStateRef, setAnimationState, stepModuleParameterValuesRef,
    setStepModuleParameterValues, setAppliedStepPoseName, motionRevisionRef
  });

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
  const effectiveRenderFormat = selectedEntrySourceFormat;
  // A fatal render-artifact error (not building) stops the loading spinner so the error surfaces.
  const artifactBlocksRender =
    isArtifactManagedFormat(effectiveRenderFormat) &&
    selectedArtifact.status === "failed" && !editingHasView;
  const meshViewerLoading =
    !!selectedEntry &&
    (selectedStepArtifactRenderPending || !artifactBlocksRender) &&
    status !== ASSET_STATUS.ERROR &&
    ((!selectedMeshMatches && !retainedPreviousStepMeshError) ||
      status === ASSET_STATUS.LOADING || selectedStepModuleLoading);
  const viewerLoading = meshViewerLoading;
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
  const selectedLoadProgress = selectedArtifactProgress || activeMeshLoadProgress || null;
  const presentationKey = selectedKey ? `${selectedKey}:${selectedMeshData ? meshState?.meshHash || selectedMeshHash : selectedMeshHash}:${selectedMeshPartial ? "partial" : "complete"}` : "";
  const [presentationState, setPresentationState] = useState(null);
  const handlePresentationChange = useCallback((next) => {
    setPresentationState(previous => previous?.file === next.file && previous?.renderMode === next.renderMode &&
      previous?.key === next.key && previous?.covering === next.covering && previous?.preparing === next.preparing ? previous : next);
  }, []);
  const presentationPending = Boolean(selectedMeshData) && (
    presentationState?.file !== selectedKey || presentationState?.key !== presentationKey || presentationState?.renderMode !== rendering ||
    presentationState?.preparing === true
  );
  const currentPreviewVisible = Boolean(editingPreview.entry && selectedMeshMatches && !selectedMeshPartial &&
    !presentationPending && Number(editingPreview.state.preview?.revision) === Number(editingPreview.state.revision));
  const completedViewFile = useRef("");
  useEffect(() => {
    if (!effectiveViewerLoading && !selectedMeshPartial && !presentationPending &&
        selectedMeshData) completedViewFile.current = selectedKey;
  }, [effectiveViewerLoading, selectedMeshPartial, presentationPending, selectedMeshData, selectedKey]);

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
    return meshAlert || viewerRuntimeAlert;
  }, [
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
    status,
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
  const drawModeActive = supportsTool(selectedEntrySourceFormat, "draw") &&
    tabToolMode === TAB_TOOL_MODE.DRAW;
  const drawing = useDrawingSession(drawModeActive, CAD_DRAWING_DEFAULTS);
  const selectionCountBase = selectedPartIds.length + selectedReferenceIds.length;

  const selectedReferenceIdsRef = useRef(selectedReferenceIds);
  const selectedPartIdsRef = useRef(selectedPartIds);
  // What the context menu's "Zoom to selection" frames, as it stands right now. It is
  // read when a menu descriptor is built — on the press, or when a tree row's menu
  // opens — so every place that menu appears offers the same item over the same target.
  const zoomSelectionRef = useRef({ partIds: EMPTY_LIST, referenceIds: EMPTY_LIST, available: false });
  const selectedEntryBuildSnapshotRef = useRef({
    fileRef: "",
    stepHash: ""
  });
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
    dynamicScene: lodSceneMayMove({ kinematics: selectedStepModuleDefinition, kinematicsLoading: selectedStepModuleLoading,
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
  const fileSessionSaveTimerRef = useRef(0);
  const activePerspectiveRef = useRef(null);
  const selectedFileSheetKeyRef = useRef("");

  const desktopRightPanelOpen = false;

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
    viewerAlert,
    viewerServerInfo
  ]);
  const selectedFileStatusLevel = useMemo(
    () => mostIntenseFileStatusLevel(selectedFileStatusItems),
    [selectedFileStatusItems]
  );
  const selectedFileHasWarningOrErrorStatus = fileStatusHasWarningsOrErrors(selectedFileStatusItems);

  const fileSheetSectionOptions = useMemo(() => ({
    // Motion contains independent Position and Animation sections; a model
    // may support either or both.
    hasStepPosePanel: Boolean(
      selectedStepModuleDefinition ||
      selectedStepModuleStatus === "loading" ||
      selectedStepModuleError
    ),
    // Animation is the Animate tool and its playbar, never an Inspector section.
    hasStepAnimationPanel: false,
    renderMode: rendering
  }), [
    selectedAnimationClipList,
    selectedAnimationError,
    selectedAnimationStatus,
    supportsMeasure,
    selectedFileSheetKind,
    selectedStepModuleDefinition,
    selectedStepModuleError,
    selectedStepModuleStatus,
    selectedStepModuleUrl,
    rendering
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
  const effectiveFileSheetOpenSectionIds = effectiveCadFileSheetOpenSectionIds;
  const handleFileSheetOpenSectionIdsChange = useCallback((nextSectionIds) => {
    setFileSheetOpenSectionIds(normalizeFileSheetOpenSectionIds(nextSectionIds, renderedSelectedFileSheetSectionIds));
  }, [renderedSelectedFileSheetSectionIds]);

  const openFileSheetSection = useCallback((sectionId, { openSheet = true } = {}) => {
    const normalizedSectionId = String(sectionId || "").trim();
    if (!normalizedSectionId || !renderedSelectedFileSheetSectionIds.includes(normalizedSectionId)) {
      return false;
    }
    if (openSheet) setTabToolsOpen(true);
    // Reveal must activate the section, even when a legacy split list already
    // contains it before another active tab.
    setFileSheetOpenSectionIds(current => current?.length === 1 && current[0] === normalizedSectionId
      ? current : [normalizedSectionId]);
    return true;
  }, [renderedSelectedFileSheetSectionIds, setTabToolsOpen]);

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
      tabToolMode
    });
  }, [
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
    // While a clip plays the authoritative time is the clock store's, not React
    // state's — the loop only writes back when playback stops.
    const snapshotAnimationElapsedSec = animationState.playing
      ? getAnimationClock()
      : animationState.elapsedSec;
    const activeCamera = renderCameraSnapshot(activePerspectiveRef.current);
    const snapshotRenderSession = createRenderSessionState({
      ...renderSession,
      cadCamera: activeCamera || renderSession.cadCamera
    });
    return createFileSessionSnapshot({
      fileKey: targetFileKey,
      entry: targetEntry,
      slices: {
        display: viewSettingsStore.getSnapshot().display,
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
        largeFile: {
          selectableTopologyEnabled: largeFileState.selectableTopologyEnabled
        }
      }
    });
  }, [
    animationState,
    buildActiveTabSnapshot,
    displaySettings,
    largeFileState,
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
    const nextDisplay = normalizeViewerDisplaySettings(sessionState?.slices?.display);
    viewSettingsStore.restore(nextDisplay);
    const nextRenderSession = createRenderSessionState({
      ...sessionState?.slices?.render,
      cadCamera: sessionState?.slices?.render?.cadCamera || sessionState?.slices?.tab?.camera
    });
    setRenderSession(nextRenderSession);
    // Only a camera this file's session actually RECORDED comes back. A file
    // opened for the first time has none, and the viewer then fits the mode
    // being opened to the model's zero pose. Synthesizing a stand-in here
    // framed the model against a bounds-radius rule of its own, tagged it with
    // the new model's key, and so suppressed that fit -- which is how a fresh
    // model opened at a pose nothing had measured.
    const restoredCamera = cameraForViewSettings(nextRenderSession.cadCamera, nextDisplay, { lightingQuality: "preview" });
    if (restoredCamera) {
      const scopedCamera = scopedWorkspacePerspective(restoredCamera, normalizedKey, entry);
      activePerspectiveRef.current = scopedCamera;
      setViewerPerspective(scopedCamera);
    }

    const stepModuleSlice = sessionState?.slices?.stepModule || null;
    if (stepModuleSlice) {
      // Definition normalization happens when the sidecar arrives. Clear the
      // losing owner's raw values immediately, including warm-file restores.
      const storedAnimation = sessionState?.slices?.animation;
      const values = storedAnimation?.enabled !== false && storedAnimation?.activeClipId
        ? {} : stepModuleSlice.parameterValues || {};
      stepModuleParameterValuesRef.current = values;
      setStepModuleParameterValues(values);
    }

    // The animation slice restores against the CLIPS this model actually
    // compiled, which is why it is resolved through restoreAnimationState rather
    // than trusted as stored.
    const animationSlice = sessionState?.slices?.animation || null;
    if (animationSlice) {
      const restoredAnimationState = restoreMotionAnimation(
        animationSlice,
        animationLoadState.url === sourceAnimationKeyForEntry(entry) ? animationLoadState.clips : null
      );
      animationStateRef.current = restoredAnimationState;
      setAnimationState(restoredAnimationState);
      setAnimationClock(restoredAnimationState.elapsedSec);
    }
  }, [
    animationLoadState,
    resolvedColorSchemeMode,
    entryMap,
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
    activePerspectiveRef.current = nextPerspective;
    setViewerPerspective(nextPerspective);
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

  // A drawing lives in the mounted editor and nowhere else, and a routine belongs
  // to its file, so a file change always ends those sessions: neither Draw nor
  // Animate carries over onto another file.
  useEffect(() => {
    setTabToolMode((current) => (current === TAB_TOOL_MODE.DRAW || current === TAB_TOOL_MODE.ANIMATE ? TAB_TOOL_MODE.REFERENCES : current));
  }, [selectedKey]);

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
    if (assetKindForRenderFormat(selectedEntryRenderAssetFormat) !== ASSET_KIND.MESH) {
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
    effectiveRenderFormat === RENDER_FORMAT.STEP &&
    selectedEntryHasReferences &&
    isAssemblyView &&
    requestedStepTreeTopologyNodeIds.length > 0;
  const selectedStepDisplayEdgesRequested =
    effectiveRenderFormat === RENDER_FORMAT.STEP &&
    selectedEntryHasDisplayEdges &&
    resolvedDisplayEdgeSettings.enabled !== false;
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
    (
      selectedStepPartRootActive ||
      assemblyStepTreeTopologyLoadingEnabled ||
      (
        plainStepReferencePickingRequested &&
        !selectedTopologyDeferredByCost &&
        !selectedTopologyWaitingForMeshCost
      )
    );

  useEffect(() => {
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
    rendering,
    requestedStepTreeTopologyNodeIds,
    selectedEntry,
    selectedEntryHasReferences,
    selectedReferencesMatch
  ]);

  useEffect(() => {
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
    rendering,
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
  const measureModeActive = supportsMeasure &&
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
  // A new measurement activates the tab that holds it.
  const measurementCountRef = useRef(0);
  useEffect(() => {
    const count = measureMeasurements.length;
    const grew = count > measurementCountRef.current;
    measurementCountRef.current = count;
    if (!grew) {
      return;
    }
    setActiveMeasureId(measureMeasurements[count - 1].id);
  }, [measureMeasurements]);

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
    previousView: completedViewFile.current === selectedKey && Boolean(selectedMeshData),
    currentPreview: currentPreviewVisible,
    error: viewerAlert || (!selectedMeshData && catalogError) || missingFileRef,
    progress: selectedLoadProgress || (editingPreview.state.phase ? { phase: editingPreview.state.phase, detail: editingPreview.state.detail } : null),
    finding: !catalogHydrated || selectedCatalogPending || fileParamSelectionPending,
    preparing: presentationPending && !effectiveViewerLoading && !selectedMeshPartial,
  });
  // A routine that failed to load has no Animate tool to say so on: it is reported
  // beside the filename instead.
  const annotationAlert = selectedAnimationError ? {
    severity: "warning", blocking: false,
    summary: "Animation unavailable",
    title: "Animation unavailable",
    tooltip: "The shape is visible, but its animation could not be loaded.",
    message: "The geometry is visible, but its animation could not be loaded, so the Animate tool is not offered.",
    details: `File: ${fileKey(selectedEntry)}\n${selectedAnimationError}`,
  } : null;
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
    renderMode: rendering,
    editingState: editingAvailable ? editingPreview.state : null,
    savedAs: "STEP file",
    showingPreview: currentPreviewVisible,
    qualityStatus: viewportQualityStatus,
    hasGeometry: Boolean(selectedMeshData && !selectedMeshPartial),
    reloading: viewerReloading
  });
  const fileStatusAlert = resolveFileStatusAlert(fileStatus, viewerAlert, annotationAlert);
  const currentFileStatusAlertKey = fileStatusAlertKey(fileKey(selectedEntry), fileStatusAlert);
  useEffect(() => {
    setViewerAlertOpen(false);
  }, [currentFileStatusAlertKey]);
  const filenameLoadActivity = useMemo(() => fileStatus ? { loading: fileStatus.busy === true, label: fileStatus.label, title: fileStatus.title, tone: fileStatus.tone, onActivate: fileStatusAlert ? () => setViewerAlertOpen(true) : undefined } : null, [fileStatus?.busy, fileStatus?.label, fileStatus?.title, fileStatus?.tone, Boolean(fileStatusAlert)]);
  useFileActivityReport(filenameLoadActivity, onActivityChange);
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
  // Shown instead of the ref when the ref will not fit. The kit's bottom action decides that by
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
      openSheet: shouldOpenFileSheetForSelectionReveal({ isDesktop: isWideLayout, source })
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

  const ensureSelectTool = useCallback(() => {
    setTabToolMode(current => current === TAB_TOOL_MODE.REFERENCES ? current : TAB_TOOL_MODE.REFERENCES);
  }, []);

  const toggleReferenceSelection = useCallback((referenceId, { multiSelect = false, source = "viewer" } = {}) => {
    if (stepInteractionBlocked || stepModuleTreeSelectionDisabled) {
      return;
    }
    ensureSelectTool();
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
  // Rebuilds keep the previous same-file mesh visible until its replacement is
  // ready. Observe that mesh's document revision while interaction is blocked.
  const displayedResourceRef = useRef(promptResource);
  if (!retainingPreviousStepMesh) displayedResourceRef.current = promptResource;
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
    ensureSelectTool();
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
    ensureSelectTool();
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

  // A selection exists only while Select is the tool. Leaving Select drops it, in
  // the viewport and the Model tree alike; choosing something in the tree under
  // another tool comes back to Select first (`ensureSelectTool`), so this effect
  // never sees that selection under the tool it was leaving.
  useEffect(() => {
    if (tabToolMode !== TAB_TOOL_MODE.REFERENCES) clearAssemblySelectionForFocus();
  }, [tabToolMode, clearAssemblySelectionForFocus]);

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

  const handleViewportContextMenuOpenChange = useCallback((open) => {
    if (!open) setViewerContextMenu(null);
  }, []);

  useEffect(() => {
    setViewerContextMenu(null);
  }, [selectedKey]);

  // The viewport's menu belongs to Select. Leaving the tool takes an open one
  // with it, so no item can outlive the tool it was offered under.
  useEffect(() => {
    if (tabToolMode !== TAB_TOOL_MODE.REFERENCES) setViewerContextMenu(null);
  }, [tabToolMode]);

  // Right-clicking empty space asks about the model as a whole: reveal what is
  // hidden, open or close the tree, and frame it again. The framing group is always
  // worth offering — a press on the backdrop is how somebody who has zoomed off the
  // model gets it back — so this menu always opens over a loaded model, and only the
  // show/expand items come and go with what they could do.
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
    const showShowAll = hasPartsMenu && hiddenPartIds.length > 0;
    const expandAllDisabled = expansionState.collapsedExpandableTreeNodeIds.length < 1;
    const collapseAllDisabled = expandedStepTreeNodeIds.length < 1;
    const showExpandCollapse = hasPartsMenu && (expansionState.showExpandCollapse || expandedStepTreeNodeIds.length > 0);
    setViewerContextMenu({
      x: Number(clientX) || 0,
      y: Number(clientY) || 0,
      global: true,
      label: "Viewer",
      hidden: true,
      zoomSelectionAvailable: zoomSelectionRef.current.available,
      showShowAll,
      showExpandCollapse: showExpandCollapse && !(expandAllDisabled && collapseAllDisabled),
      collapsedExpandableTreeNodeIds: expansionState.collapsedExpandableTreeNodeIds,
      expandedExpandableTreeNodeIds: expandedStepTreeNodeIds,
      expandAllDisabled,
      collapseAllDisabled
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

  /**
   * The part menu for ONE node of the model, as a descriptor
   * (`AssemblyPartMenuItems` renders it). The viewport's secondary tap and the
   * Features tree's row menu both ask for it, so the two are the same menu over
   * the same node by construction rather than by two lists kept in step.
   *
   * `renderPartId` is the leaf the pointer actually landed on, when the menu was
   * asked for in the viewport; a tree row is its own node.
   */
  const assemblyNodeMenu = useCallback((nodeId, renderPartId = "") => {
    const normalizedNodeId = String(nodeId || "").trim();
    if (!normalizedNodeId) {
      return null;
    }
    const pickedPartId = String(renderPartId || "").trim() || normalizedNodeId;
    const node = assemblyPartMap.get(normalizedNodeId) || findAssemblyNode(assemblyRoot, normalizedNodeId) || null;
    const label = String(
      node?.displayName ||
      node?.name ||
      node?.label ||
      normalizedNodeId
    ).trim();
    const leafIds = renderPartIdsForAssemblySelection(normalizedNodeId, pickedPartId);
    const hidden = leafIds.length > 0 && leafIds.every((id) => hiddenPartIds.includes(id));
    const focused = focusedAssemblyNodeIds.includes(normalizedNodeId);
    const selected = selectedPartIdsRef.current.includes(normalizedNodeId);
    const actionNodeIds = uniqueStringList([
      ...selectedPartIdsRef.current
        .map((id) => String(id || "").trim())
        .filter(Boolean),
      normalizedNodeId
    ]);
    const expansionState = buildStepTreeExpansionMenuState({
      root: displayStepTreeRoot,
      isAssemblyView,
      expandedTreeNodeIds: expandedStepTreeNodeIds,
      loadableTreeNodeIds: loadableStepTreeTopologyNodeIds,
      actionNodeIds
    });
    const contextCopyReference = stepTreeCopyReferenceMap.get(normalizedNodeId) ||
      copyReferenceForStepTreeNodeSelection(node, normalizedNodeId, "assembly-part") ||
      copyReferenceForAssemblyPartSelection(node, normalizedNodeId) ||
      copyReferenceForRawSelectorSelection(normalizedNodeId, "assembly-part");
    const { lines } = copyPayloadWithSelectedIdFallback(buildSelectionCopyPayload({
      references: contextCopyReference ? [contextCopyReference] : [],
      parts: [],
      entry: selectedEntry
    }), {
      selectedPartIds: actionNodeIds,
      copyReferenceMap: stepTreeCopyReferenceMap
    });
    return {
      nodeId: normalizedNodeId,
      renderPartId: pickedPartId,
      label,
      zoomSelectionAvailable: zoomSelectionRef.current.available,
      selected,
      hidden,
      focused,
      actionNodeIds,
      actionCount: actionNodeIds.length || 1,
      copyText: lines[0] || "",
      selectDisabled: !selected && hidden,
      showIsolate: isAssemblyView,
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
      showExpandCollapse: expansionState.showExpandCollapse,
      collapsedActionNodeIds: expansionState.collapsedActionNodeIds,
      expandedActionNodeIds: expansionState.expandedActionNodeIds,
      collapsedExpandableTreeNodeIds: expansionState.collapsedExpandableTreeNodeIds,
      expandedExpandableTreeNodeIds: expansionState.expandedExpandableTreeNodeIds,
      expandSelectedDisabled: expansionState.collapsedActionNodeIds.length < 1,
      collapseSelectedDisabled: expansionState.expandedActionNodeIds.length < 1,
      expandAllDisabled: expansionState.collapsedExpandableTreeNodeIds.length < 1,
      collapseAllDisabled: expansionState.expandedExpandableTreeNodeIds.length < 1
    };
  }, [
    assemblyPartMap,
    assemblyRoot,
    displayStepTreeRoot,
    expandedStepTreeNodeIds,
    focusedAssemblyNodeIds,
    hiddenPartIds,
    isAssemblyView,
    loadableStepTreeTopologyNodeIds,
    renderPartIdsForAssemblySelection,
    selectedEntry,
    stepTreeCopyReferenceMap
  ]);

  // Only ever reached under Select (the viewport's menu is offered by that tool alone), so
  // nothing it offers can contradict the tool.
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
        zoomSelectionAvailable: zoomSelectionRef.current.available,
        showIsolate: false,
        showHideOther: false,
        showVisibility: false,
        showHideAll: false
      });
      return;
    }
    if (!viewerInAssemblyMode) {
      openGlobalViewerContextMenu({ clientX, clientY });
      return;
    }
    const menu = assemblyNodeMenu(resolvePickedAssemblyPartId(pickedPartId), pickedPartId);
    if (!menu) {
      openGlobalViewerContextMenu({ clientX, clientY });
      return;
    }
    setViewerContextMenu({ x: Number(clientX) || 0, y: Number(clientY) || 0, ...menu });
  }, [
    assemblyNodeMenu,
    effectiveActiveReferenceMap,
    isViewerTopologyReference,
    openGlobalViewerContextMenu,
    resolvePickedAssemblyPartId,
    selectedEntry,
    stepTreeCopyReferenceMap,
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

  // "Zoom to fit": frame the whole model again from where the camera looks now. It is
  // the viewport's one framing act — the live `resetCamera` command is the same call.
  const zoomToFitModel = useCallback(() => {
    if (!viewerRef.current?.resetZoom?.()) {
      setCopyStatus("CAD Viewer camera not ready");
    }
  }, []);

  // "Zoom to selection": frame what is selected right now, whichever menu asked and
  // whatever node it was asked over. The item is offered only where there IS a
  // selection, so finding nothing to frame here is a real failure and says so.
  const zoomToSelection = useCallback(() => {
    const ids = (list) => uniqueStringList(
      (Array.isArray(list) ? list : []).map((id) => String(id || "").trim()).filter(Boolean)
    );
    const partIds = ids(zoomSelectionRef.current.partIds);
    const referenceIds = ids(zoomSelectionRef.current.referenceIds);
    if (!(partIds.length || referenceIds.length)
      || !viewerRef.current?.zoomToFitSelection?.({ partIds, referenceIds, animate: true })) {
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

  const addPartMenuReferenceToPrompt = useCallback((menu) => {
    const copyText = String(menu?.copyText || "")
      .split("\n")
      .map((line) => canonicalCadRefCopyText(line))
      .filter(Boolean)
      .join("\n");
    if (!copyText) {
      setCopyStatus("No selector ref is available for this node");
      return;
    }
    addReferenceText(copyText);
  }, [addReferenceText]);

  /**
   * The actions behind the one part menu, wherever it was opened: the viewport
   * under Select, and a Features tree row under any tool. A tree row's menu can
   * therefore ask for something the active tool cannot show, so every action
   * lands in Select first — exactly what clicking a tree row already does.
   */
  const partMenuActions = useMemo(() => Object.fromEntries(Object.entries({
    onAddToPrompt: addPartMenuReferenceToPrompt,
    onCopyReference: copyViewerContextMenuReference,
    onSelect: selectViewerContextMenuNode,
    onIsolate: focusViewerContextMenuNode,
    onExitAllIsolate: handleExitIsolate,
    onHideOther: hideOtherViewerContextMenuNode,
    onHideAll: hideAllViewerContextMenuNodes,
    onHide: hideViewerContextMenuNode,
    onReveal: revealViewerContextMenuNode,
    onExpandSelected: expandSelectedViewerContextMenuNodes,
    onCollapseSelected: collapseSelectedViewerContextMenuNodes,
    onExpandAll: expandAllViewerContextMenuNodes,
    onCollapseAll: collapseAllViewerContextMenuNodes,
    onZoomFit: zoomToFitModel,
    onZoomSelection: zoomToSelection
  }).map(([name, action]) => [name, (menu) => { ensureSelectTool(); return action(menu); }])), [
    addPartMenuReferenceToPrompt,
    copyViewerContextMenuReference,
    selectViewerContextMenuNode,
    focusViewerContextMenuNode,
    handleExitIsolate,
    hideOtherViewerContextMenuNode,
    hideAllViewerContextMenuNodes,
    hideViewerContextMenuNode,
    revealViewerContextMenuNode,
    expandSelectedViewerContextMenuNodes,
    collapseSelectedViewerContextMenuNodes,
    expandAllViewerContextMenuNodes,
    collapseAllViewerContextMenuNodes,
    zoomToFitModel,
    zoomToSelection,
    ensureSelectTool
  ]);

  // The viewport's menu, asked for at the moment of a secondary tap under Select: resolve what
  // is under the press into the one menu descriptor (a part, a topology reference, or the model
  // as a whole), remember it so the part stays marked while the menu is up, and hand the shell
  // the entries. Nothing to offer is an empty answer, and the shell opens nothing.
  const viewportContextMenuItems = useCallback((press, referenceId) => {
    handleModelReferenceContext(referenceId, press);
    const menu = viewerContextMenuRef.current;
    return menu ? viewportMenuEntries(menu, { actions: {
      ...partMenuActions,
      // Offered only where the host has somewhere to put it.
      onAddToPrompt: hostReference?.canAddToPrompt ? partMenuActions.onAddToPrompt : undefined
    } }) : null;
  }, [handleModelReferenceContext, hostReference, partMenuActions]);

  const handleSelectEntry = useCallback((key) => {
    const next = entryMap.get(key);
    onOpenFile?.(next ? cadFileParamForEntry(next) : key);
  }, [entryMap, onOpenFile]);

  const handleSelectTabToolMode = useCallback((mode) => {
    setViewerAlertOpen(false);
    // Anything unrecognized falls back to selection rather than sticking the
    // viewer in a mode with no tool behind it.
    const normalizedMode = CAD_TOOL_MODES.normalize(mode);
    // Measure and Draw are sessions: asking for the active one again ends it. (The Measure
    // button itself spends its second press on the snap menu; see FloatingToolBar.js.)
    setTabToolMode(current => CAD_TOOL_MODES.next(current, normalizedMode));
    if (
      selectedEntry &&
      selectedEntryHasReferences &&
      normalizedMode === TAB_TOOL_MODE.MEASURE && topologyTarget
    ) {
      loadFilterTopology(topologyTarget);
    }
  }, [selectedEntry, selectedEntryHasReferences, topologyTarget, loadFilterTopology]);

  const handlePerspectiveChange = useCallback((nextPerspective) => {
    if (previewMode) { onLodCameraMoved(); return; }
    const normalizedPerspective = clonePerspectiveSnapshot(nextPerspective);
    if (normalizedPerspective) {
      activePerspectiveRef.current = normalizedPerspective;
      scheduleActiveFileSessionSave();
    }
    // Camera moved: give the LOD scheduler a sample (it debounces internally).
    onLodCameraMoved();
  }, [onLodCameraMoved, previewMode, scheduleActiveFileSessionSave]);

  const handleViewModeChange = viewSettingsStore.selectPreset;

  const handleRenderEnabledChange = useCallback((enabled) => {
    handleViewModeChange(enabled ? "render" : "solid");
  }, [handleViewModeChange]);

  const handleDisplayReset = viewSettingsStore.reset;

  // An inspection highlight is a narrower selection than the tree's, and is what the
  // person is actually looking at, so it wins.
  const zoomSelectionPartIds = inspectionHighlight ? inspectionHighlight.partIds || EMPTY_LIST : viewerSelectedPartIds;
  const zoomSelectionReferenceIds = inspectionHighlight ? inspectionHighlight.faceIds || EMPTY_LIST : selectedReferenceIds;
  zoomSelectionRef.current = {
    partIds: zoomSelectionPartIds,
    referenceIds: zoomSelectionReferenceIds,
    available: Boolean(zoomSelectionPartIds.length || zoomSelectionReferenceIds.length)
  };

  useCadWorkspaceShortcuts({
    viewerElement,
    selectionActive: selectedPartIds.length > 0 || selectedReferenceIds.length > 0,
    onClearSelection: clearAssemblySelection,
    copyStatus,
    screenshotStatus,
    setCopyStatus,
    setScreenshotStatus,
    previewMode,
    inspectionEnabled: !previewMode,
    viewerAlertOpen,
    tabToolsOpen,
    isDesktop: isWideLayout,
    filesPanelOpen,
    tabToolMode,
    measureDraftActive: Boolean(measureRulerState?.draft?.anchor),
    onCancelMeasureDraft: handleMeasureCancelDraft,
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

  // App tools bind to this actual mounted viewport, never catalog metadata.
  const liveRuntimeRef = useRef(null);
  liveRuntimeRef.current = {
    readState() {
      const displayedResource = displayedResourceRef.current;
      const text = inspectionHighlight ? stepGeometryPromptText(inspectionHighlight, {
        referenceMap: effectiveActiveReferenceMap, parts: selectedMeshData?.parts || EMPTY_LIST, entry: selectedEntry,
      }) : canonicalCopySelectionLines.join("\n");
      const references = referencesForHost(text).map(reference => ({
        resource: { ...displayedResource },
        target: reference.selector ? { kind: 'cad-selector', selectors: reference.selector.split(',') } : { kind: 'whole-resource' },
        ...(reference.label ? { label: reference.label } : {}),
      }));
      return {
        resource: { ...displayedResource }, revision: String(displayedResource.revision || ''),
        loading: Boolean(viewerLoading || stepInteractionBlocked),
        selection: references,
        selectedPartIds: [...(inspectionHighlight ? inspectionHighlight.partIds || [] : viewerSelectedPartIds)],
        selectedReferenceIds: [...(inspectionHighlight ? inspectionHighlight.faceIds || [] : selectedReferenceIdsRef.current)],
        hiddenPartIds: [...hiddenPartIds], isolatedPartIds: [...isolatedAssemblyNodeIds],
        camera: clonePerspectiveSnapshot(viewerRef.current?.getPerspective?.() || activePerspectiveRef.current),
        display: viewSettingsStore.getSnapshot().display, renderMode: viewSettingsStore.getSnapshot().display.mode === 'render' ? 'render' : 'inspect',
      };
    },
    select({ selectors, replace = true }) {
      if (stepModuleTreeSelectionDisabled) throw new Error(stepModuleTreeSelectionDisabledReason || 'Selection is unavailable for this model.');
      const names = uniqueStringList(selectors.flatMap(selector => String(selector).split(',').map(value => value.trim())).filter(Boolean));
      if (!names.length) throw new Error('Choose at least one CAD selector.');
      const selections = names.map(selector => resolveSelectorSelection(selector, {
        referenceMap: effectiveActiveReferenceMap, treeRoot: displayStepTreeRoot || stepTreeRoot,
      }));
      const missing = names.filter((_name, index) => !selections[index]);
      if (missing.length) throw new Error(`Selectors are unavailable in the displayed revision: ${missing.join(', ')}. Expand their model tree entries to load topology.`);
      if (isAssemblyView && selections.some(selection => selection.kind === 'part' && !validAssemblySelectionIdSet.has(selection.id))) {
        throw new Error('The requested assembly selection is unavailable in the displayed model.');
      }
      const parts = uniqueStringList([...(replace ? [] : selectedPartIdsRef.current), ...selections.filter(selection => selection.kind === 'part').map(selection => selection.id)]);
      const references = uniqueStringList([...(replace ? [] : selectedReferenceIdsRef.current), ...selections.filter(selection => selection.kind === 'reference').map(selection => selection.id)]);
      selectedPartIdsRef.current = parts;
      selectedReferenceIdsRef.current = references;
      setSelectedPartIds(parts);
      setSelectedReferenceIds(references);
      setSelectedWholeEntryCadRefToken('');
      setInspectionHighlight(null);
      setSelectedRenderPartIdByAssemblyPartId(current => Object.fromEntries(parts.map(id => [id, renderPartIdForAssemblySelection(id, current[id])]).filter(([, id]) => id)));
      const last = selections[selections.length - 1];
      revealStepTreeNode(last.kind === 'part' ? last.id : findStepTreeTopologyNodeIdForReference(displayStepTreeRoot, last.id) || referencePartId(effectiveActiveReferenceMap.get(last.id)), { source: 'reference' });
    },
    clearSelection() {
      selectedPartIdsRef.current = [];
      setSelectedPartIds([]);
      setSelectedRenderPartIdByAssemblyPartId({});
      clearReferenceSelection();
      setInspectionHighlight(null);
    },
    setCamera(camera) {
      const validVector = vector => Array.isArray(vector) && vector.length === 3 && vector.every(Number.isFinite);
      if (!['position', 'target', 'up'].every(key => validVector(camera?.[key]))
        || (camera.projection != null && !['perspective', 'orthographic'].includes(camera.projection))
        || ['zoom', 'focalLength', 'orthographicHalfHeight'].some(key => camera[key] != null && (!Number.isFinite(camera[key]) || camera[key] <= 0))) {
        throw new Error('Camera vectors must contain three finite numbers and camera scales must be positive.');
      }
      const nextDisplay = viewerDisplaySettingsForCamera(viewSettingsStore.getSnapshot().display, camera);
      const requestedSnapshot = clonePerspectiveSnapshot(camera);
      if (previewMode) {
        if (!viewerRef.current?.setPerspective?.(requestedSnapshot)) throw new Error('The viewer could not apply this camera.');
        return;
      }
      const snapshot = cameraForViewSettings(requestedSnapshot, nextDisplay, { lightingQuality: "preview" });
      if (!snapshot || !viewerRef.current?.setPerspective?.(snapshot, { resetZoomBaseline: true })) throw new Error('The viewer could not apply this camera.');
      const scoped = scopedWorkspacePerspective(snapshot, selectedKey, selectedEntry);
      setRenderSession(createRenderSessionState({ cadCamera: snapshot }));
      viewSettingsStore.restore(nextDisplay);
      setViewerPerspective(scoped);
      handlePerspectiveChange(scoped);
    },
    // What the context menu's "Zoom to fit" does: frame the model again, without
    // turning the camera. The name is the host protocol's ("cad-reset-camera").
    resetCamera() {
      if (!viewerRef.current?.resetZoom?.()) throw new Error('The viewer camera is unavailable.');
    },
    setDisplaySettings(patch) {
      viewSettingsStore.patch(patch);
    },
    setRenderMode(enabled) { handleRenderEnabledChange(enabled); },
    capture() {
      if (!viewerRef.current?.captureScreenshotBlob) throw new Error('The viewer cannot capture this model yet.');
      return viewerRef.current.captureScreenshotBlob();
    },
  };
  useEffect(() => {
    if (!live) return;
    return attachCadLiveBinding(live, () => liveRuntimeRef.current);
  }, [live]);

  // Publishing navbar actions must not feed parent renders back into this
  // renderer. Stable commands read the current mounted viewport at invocation.
  const navigationHandlersRef = useRef(null);
  navigationHandlersRef.current = { capture: handleCapture };
  const hasViewportContent = Boolean(selectedViewportContent);
  useEffect(() => {
    const actions = selectedKey ? [{ id: "snapshot", label: "Take snapshot", icon: Camera,
      disabled: viewerLoading || stepInteractionBlocked || !hasViewportContent || !promptAvailable,
      onInvoke: () => navigationHandlersRef.current.capture() }] : [];
    onNavigationActionsChange?.(actions);
    return () => onNavigationActionsChange?.([]);
  }, [onNavigationActionsChange, selectedKey,
    viewerLoading, stepInteractionBlocked, hasViewportContent, promptAvailable]);

  const selectionToolActive = tabToolMode === TAB_TOOL_MODE.REFERENCES;
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
  // Every CAD format shares the View settings and camera contract.
  const renderDisplaySettings = resolvedScene.display;
  const settingsTabs = [buildDisplaySettingsTab({
    features: viewFeatures,
    viewSettings: displaySettings,
    hostAppearance: resolvedColorSchemeMode,
    lightingQuality: "preview",
    resolvedView: desiredScene.view,
    onViewSettingsPatch: viewSettingsStore.patch,
    onGroupEnabledChange: viewSettingsStore.setEnabled,
    onModeChange: handleViewModeChange,
    onViewReset: handleDisplayReset,
    clipBounds: selectedMeshData?.bounds || null,
    explodeDisabled: Boolean(selectedMeshData) && explodablePartCount(selectedMeshData) <= 1,
    edgeStatus: displayEdgeStatus,
    edgeError: displayEdgeError,
  })];

  // Both presentations consume the same runtime snapshots and commands.
  const stepPositionControls = {
    status: selectedStepModuleStatus,
    error: selectedStepModuleError,
    definition: selectedStepModuleDefinition,

    parameterValues: stepModuleParameterValues,
    onParameterChange: handleStepModuleParameterChange,
    onResetParameters: handleResetParameters,
    onApplyPose: handleApplyPose,
    activePose: animationState.enabled !== false ? "" : appliedStepPoseName,
    positionActive: !selectedAnimationRuntime,
    onResetMotion: resetStepMotion,

    onCopyParams: handleCopyParameters,
    onPasteParams: handlePasteParameters
  };
  const stepAnimationControls = {
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
    onPlayToggle: handleAnimationPlayToggle,
    onRestart: handleAnimationRestart,
    onScrub: handleAnimationScrub,
    onSpeedChange: handleAnimationSpeedChange,
    onLoopToggle: handleAnimationLoopToggle,
    resetModel: resetStepMotion
  };
  // Only a STEP carries routines here; every other format this renderer shows has none.
  const viewportAnimation = selectedFileSheetKind === "step" ? stepAnimationControls : null;
  // Animate is one mode with two ways in: the tool, and fullscreen, which is that
  // tool with the rest of the viewer put away (or no tool, without animation).
  const animationAvailable = animationControlsHaveContent(viewportAnimation);
  const animateToolActive = !previewMode && animationAvailable && tabToolMode === TAB_TOOL_MODE.ANIMATE;
  const animateModeActive = animationAvailable && (previewMode || animateToolActive);
  useEffect(() => {
    if (!animationAvailable) setTabToolMode(current => current === TAB_TOOL_MODE.ANIMATE ? TAB_TOOL_MODE.REFERENCES : current);
  }, [animationAvailable]);
  // A routine owns the model's pose only inside the mode. Outside it the clip is
  // released — stopped, rewound, the pose back with Position — so selection,
  // topology and Position never meet an animated model and need no special case
  // for one. Nothing of the playback survives: coming back starts from the start,
  // and a restored session that was mid-routine is released the same way.
  const releaseAnimation = selectedFileSheetKind === "step" ? releaseStepAnimation : null;
  const animationOwnsPose = animationAvailable && viewportAnimation?.enabled !== false;
  useEffect(() => {
    if (!animateModeActive && animationOwnsPose) releaseAnimation?.();
  }, [animateModeActive, animationOwnsPose, releaseAnimation]);

  // Pose: drag the joints by their handles. Present only where something can be
  // driven (a STEP's mate DOFs). The handles are rebuilt from the pose on screen,
  // so sliders, presets, Reset and a handle up the chain all carry them along.
  const stepPoseDefinition = selectedFileSheetKind === "step" ? selectedStepParameterRuntime?.definition || null : null;
  const poseAvailable = stepPosableDofs(stepPoseDefinition).length > 0;
  const poseToolActive = !previewMode && poseAvailable && tabToolMode === TAB_TOOL_MODE.POSE;
  useEffect(() => {
    if (!poseAvailable) setTabToolMode(current => current === TAB_TOOL_MODE.POSE ? TAB_TOOL_MODE.REFERENCES : current);
  }, [poseAvailable]);
  // A mated child's label names its parts, and the mesh here is the model at
  // rest (the viewer poses display records, never this data): the child's centre.
  const stepPoseSelectorRuntime = selectedStepParameterRuntime?.selectorRuntime || null;
  const stepPoseFeatures = useMemo(() => (stepPoseDefinition && poseToolActive
    ? resolveStepModuleFeatures(stepPoseDefinition, { meshData: selectedMeshData, selectorRuntime: stepPoseSelectorRuntime })
    : null), [stepPoseDefinition, poseToolActive, selectedMeshData, stepPoseSelectorRuntime]);
  const jointHandles = useMemo(() => {
    if (!poseToolActive) return null;
    return stepJointHandles({
      definition: stepPoseDefinition,
      parameterValues: selectedStepParameterRuntime.parameterValues,
      features: stepPoseFeatures,
      onParameterChange: handleStepModuleParameterChange
    });
  }, [poseToolActive, stepPoseDefinition, selectedStepParameterRuntime, stepPoseFeatures, handleStepModuleParameterChange]);

  return (
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
                be read (kit/look/chromeBackdrop.js). */}
            <div
              className="@container/cad-viewport pointer-events-none relative min-w-0 flex-1 overflow-hidden"
              data-cad-scene-backdrop={sceneBackdrop}
              style={{ backgroundColor: sceneBackdrop }}
            >
              <div className="pointer-events-auto absolute inset-0 z-0">
                <StepViewport
                ref={viewerRef}
                onReload={onReload}
                viewUpdate={viewUpdate}
                onLodCameraChange={onLodCameraMoved}
                onMeshSourceAdoption={handleDisplayMeshAdoption}
                renderPartsIndividually={
            Boolean(selectedStepParameterRuntime) || Boolean(selectedAnimationRuntime) ||
            Boolean(Object.keys(selectedDisplayMeshData?.appearance?.materials || {}).length)
          }
                stepParameters={selectedStepParameterRuntime}
                stepAnimation={selectedAnimationRuntime}
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
                receiveShadows={resolvedScene.view.lighting.enabled}
                renderMode={resolvedScene.render.enabled}
                renderConfiguration={resolvedScene.render.configuration}
                quality={resolvedScene.quality}
                displaySettings={renderDisplaySettings}
                previewMode={previewMode}
                previewOrbitSpeed={previewOrbitSpeed}
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
                viewerMode={viewerMode}
                assemblyPickingActive={viewerInAssemblyMode}
                assemblyParts={viewerAssemblyRenderParts}
                hiddenPartIds={viewerHiddenPartIds}
                selectedPartIds={inspectionHighlight ? inspectionHighlight.partIds || [] : viewerSelectedPartIds}
                hoveredPartId={viewerHoveredPartIds}
                hoveredReferenceId={effectiveHoveredReferenceId}
                selectedReferenceIds={inspectionHighlight ? inspectionHighlight.faceIds : selectedReferenceIds}
                selectorRuntime={effectiveSelectorRuntime}
                displayEdgeRuntime={selectedDisplayEdgeRuntime}
                pickableFaces={measureModeActive ? (["all", "faces"].includes(measureSelectionFilter) ? viewerPickableFaces : EMPTY_LIST) : filteredViewerFaces}
                pickableEdges={measureModeActive ? (["all", "edges"].includes(measureSelectionFilter) ? viewerPickableEdges : EMPTY_LIST) : filteredViewerEdges}
                pickableVertices={(measureModeActive ? ["all", "points"].includes(measureSelectionFilter) : selectionFilter === "all") ? viewerPickableVertices : EMPTY_LIST}
                focusedPartIds={viewerFocusedPartIds}
                drawToolActive={drawToolActive}
                measureModeActive={measureModeActive}
                drawing={drawing}
                handleScreenshotCopy={handleCapture}
                handlePerspectiveChange={handlePerspectiveChange}
                handleModelHoverChange={handleModelHoverChange}
                handleModelReferenceActivate={handleModelReferenceActivate}
                handleModelReferenceDoubleActivate={handleModelReferenceDoubleActivate}
                contextMenuItems={selectionToolActive ? viewportContextMenuItems : null}
                onContextMenuOpenChange={handleViewportContextMenuOpenChange}
                onMeasurePick={handleMeasurePick}
                onMeasureHoverPoint={handleMeasureHoverPoint}
                activeMeasurementId={inspectionHighlight?.measurement?.id || activeMeasureId}
                measureState={inspectionHighlight?.measurement ? { measurements: [inspectionHighlight.measurement] } : measureRulerState}
                handleViewerAlertChange={handleViewerAlertChange}
                handleStepModuleTransformDetectedChange={handleStepModuleTransformDetectedChange}
                selectionCount={selectionCount}
                copyButtonLabel={copyButtonLabel}
                copyButtonCountLabel={copyButtonCountLabel}
                animateToolActive={animateToolActive}
                jointHandles={jointHandles}
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

              {previewMode && <FullscreenToolbar key={selectedKey} surface={hostElement}
                orbitSpeed={previewOrbitSpeed} onOrbitSpeedChange={setPreviewOrbitSpeed}
                animation={viewportAnimation}
                disabled={viewerLoading || stepInteractionBlocked || !selectedMeshData}
                onExit={onExitFullscreen}/>}

              {animateToolActive && (
                <ViewportAnimationBar key={selectedKey} runtime={viewportAnimation} avoidViewControl
                  className="pointer-events-auto"
                  disabled={viewerLoading || stepInteractionBlocked || !selectedMeshData}/>
              )}

              <FloatingToolBar
                previewMode={previewMode}
                renderMode={rendering}
                selectedEntry={selectedEntry}
                renderFormat={effectiveRenderFormat}
                floatingCadToolbarPosition={floatingCadToolbarPosition}
                selectionFilter={supportsTopology ? selectionFilter : null}
                onSelectionFilterChange={value => { setSelectionFilter(value); handleSelectTabToolMode("references"); }}
                selectionFilterNotice={selectionFilterNotice}
                selectionToolActive={selectionToolActive}
                referenceSelectionPending={referenceSelectionPending}
                referenceSelectionUnavailable={referenceSelectionUnavailable}
                referenceSelectionDeferred={selectedTopologyDeferredByCost}
                drawToolActive={drawToolActive}
                measureModeActive={measureModeActive}
                measureSnapFilter={supportsTopology && supportsMeasure ? measureSelectionFilter : null}
                onMeasureSnapFilterChange={value => {
                  setMeasureSelectionFilter(value); handleMeasureCancelDraft();
                  if (topologyTarget) loadFilterTopology(topologyTarget);
                }}
                measurementPanel={supportsMeasure ? <MeasurePanel
                  measurements={measureMeasurements} activeId={activeMeasureId}
                  onActivate={setActiveMeasureId} onDelete={handleMeasureDelete} onClear={handleMeasureClear}
                /> : null}
                measureSupported={supportsMeasure}
                measureDisabled={measureToolDisabled}
                animateAvailable={animationAvailable}
                animateToolActive={animateToolActive}
                poseAvailable={poseAvailable}
                poseToolActive={poseToolActive}
                handleSelectTabToolMode={handleSelectTabToolMode}
                viewerLoading={viewerLoading}
                selectedMeshData={selectedMeshData}
                drawing={drawing}
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

              <ViewUpdateStatus status={viewUpdate.status} onRetry={viewUpdate.retry} className="absolute bottom-3 left-3 z-30" />
              <ViewerLoadingOverlay
                loading={presentationState?.file === selectedKey && presentationState?.covering ? null : loading}
                previewMode={previewMode}
                operationKey={selectedKey || explicitFileParam}
              />
            </div>

            {selectedFileSheetKind === "step" ? (
              <StepFileSheet
                selectedMeshData={selectedDisplayMeshData}
                selectedSourceAppearance={selectedSourceAppearance}
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
                menuForNode={assemblyNodeMenu}
                partMenuActions={partMenuActions}
                onTogglePartVisibility={togglePartVisibility}
                hideOtherSelectedParts={handleHideOtherSelectedParts}
                hideAllParts={handleHideAllParts}
                showAllHiddenParts={handleShowAllHiddenParts}
                exitIsolate={handleExitIsolate}
                stepModule={stepPositionControls}
                stepAnimation={stepAnimationControls}
                viewerServerInfo={viewerServerInfo}
                suppressDynamicMetadataStatus={selectedArtifactGenerating}
                statusItems={selectedFileStatusItems}
                renderMode={rendering}
                settingsTabs={settingsTabs}
                openSectionIds={effectiveFileSheetOpenSectionIds}
                onOpenSectionIdsChange={handleFileSheetOpenSectionIdsChange}
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
  );
}

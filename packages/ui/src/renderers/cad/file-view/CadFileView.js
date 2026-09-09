"use client";

import { TutorialTipsContext } from "../workbench/tutorialTips.js";
import { FileSheetTabPreferencesContext } from "../workbench/fileSheetTabPreferences.js";
import * as THREE from "three";
import { startTransition, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { ArrowLeftRight, ArrowRight, Circle, Eraser, FileText, Minus, PaintBucket, PenTool, Square } from "lucide-react";
import { CAD_PANEL, EmptyState } from "@hardcore/ui/navigation";
import { cn } from "@hardcore/ui/utils";
import CadRenderPane from "../components/workbench/CadRenderPane.js";
import { useViewportLod } from "../render/useViewportLod.js";
import {
  ThemeEditorPanel,
  buildDisplaySettingsTab
} from "../components/workbench/ThemeSettingsPopover.js";
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
import StepFileSheet from "../components/workbench/StepFileSheet.js";
import { FileSheetPortalContext, HostPanelSlotContext } from "../components/workbench/FileSheet.js";
import { poseValuesForPreset } from "../components/workbench/PoseControlsSection.js";
import StatusToast from "../components/workbench/StatusToast.js";
import UrdfFileSheet from "../components/workbench/UrdfFileSheet.js";
import ViewerAlertDialog from "../components/workbench/ViewerAlertDialog.js";
import ViewerLoadingOverlay from "../components/workbench/ViewerLoadingOverlay.js";
import {
  ARTIFACT_PROGRESS_POLL_MS,
  formatArtifactProgress,
  normalizeArtifactProgress
} from "../workbench/artifactProgress.js";
import FloatingToolBar from "../components/workbench/FloatingToolBar.js";
import { useCadAssets } from "../components/workbench/hooks/useCadAssets.js";
import { resolveDesktopPanelWidth } from "./fileViewState.js";
import { useCadWorkspaceSelection } from "../components/workbench/hooks/useCadWorkspaceSelection.js";
import { useCadWorkspaceSelectors } from "../components/workbench/hooks/useCadWorkspaceSelectors.js";
import { useCadWorkspaceShortcuts } from "../components/workbench/hooks/useCadWorkspaceShortcuts.js";
import {
  CUSTOM_THEME_ID,
  getThemePresetIdForSettings,
  normalizeThemeSettings
} from "@hardcore/core/lib/themeSettings.js";
import {
  displayModeForcesEdges,
  displayModeIsWireframe,
  normalizeDisplayEdgeSettings,
  normalizeDisplaySettings
} from "@hardcore/core/lib/displaySettings.js";
import { clonePerspectiveSnapshot } from "@hardcore/core/lib/perspective.js";
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
  fileSheetSectionIdsWithOpenSection,
  normalizeFileSheetOpenSectionIds,
  renderedFileSheetSectionIds,
  shouldOpenFileSheetForSelectionReveal
} from "../workbench/fileSheetSections.js";
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
  renderFormatLabel,
  supportsTool,
  viewportContentKind,
  ASSET_KIND,
  PARAMETER_SOURCE,
  VIEWPORT_CONTENT
} from "@hardcore/core/lib/renderCapabilities.js";
import {
  buildViewerMeshAlert
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
  orderedStringListEqual,
  parseAssemblyPartReferenceSelectionId,
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
  entryRenderModuleUrl,
  entryUrdfAssetHash
} from "@hardcore/core/lib/entryAssets.js";
import {
  hasStepGlbByteCost,
  isLargeMeshData,
  isLargeStepGlbEntry
} from "@hardcore/core/lib/render/meshCost.js";
import { cloneDrawingStrokes, cloneTabSnapshot, createTabRecord, drawingStrokesEqual,
  tabSnapshotEqual, createThemeState } from "../workbench/state.js";
import { createFileSessionSnapshot, normalizeFileSessionState } from "../workbench/fileSessionState.js";
import { toFiniteNumber } from "../workbench/valueUtils.js";
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
  URDF_JOINT_ANIMATION_DURATION_MS,
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
  flattenAssemblyNodes,
  flattenAssemblyLeafParts,
  leafPartIdsForAssemblySelection,
  resolveAssemblyPickedPartId
} from "@hardcore/core/lib/assembly/meshData.js";
import {
  assemblyNodeContainsNode,
  minimalAssemblyIsolationNodeIds,
  selectedReferenceIdsOutsideFocusedAssemblyNodes,
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
import { loadKinematicsModuleDefinition } from "@hardcore/core/common/kinematicsModule.js";
import { loadRenderModule, validateRenderModuleClips } from "@hardcore/core/common/renderModule.js";
import {
  normalizeParameterValue,
  normalizeParameterValues
} from "@hardcore/core/common/parameters.js";
import { copyTextToClipboard, readTextFromClipboard } from "@hardcore/ui/clipboard";
import { HostReferenceContext, referenceLabel, referencesFromCopyText, resolveSelectorSelection } from "./hostReference.js";

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
import { resolveCadThemeSettings, useChromeBackdropColor } from "./cadTheme.js";
import {
  addReferenceLookupKeys,
  buildStepTreeCopyReferenceMap,
  buildStepTreeExpansionMenuState,
  childAssemblyNodeIdForPickedLeaf,
  collectStepTreeRevealExpansionIds,
  collectStepTreeSubtreeIds,
  collectStepTreeTopologyLoadableNodeIds,
  copyPayloadWithSelectedIdFallback,
  copyReferenceForAssemblyPartSelection,
  copyReferenceForRawSelectorSelection,
  copyReferenceForStepTreeNodeSelection,
  copyableStepTreeNodeForWorkspace,
  findStepTreeTopologyNodeIdForReference,
  visibleStepTreeTopologyReferenceIdsForWorkspace
} from "./stepTreeSelection.js";

// The shared renderer consumes one prepared entry. FileViewer owns navigation,
// panel placement and persistence; the connection owns catalog subscriptions.
export default function CadFileView(props) {
  const clock = useMemo(() => createAnimationClock(), []);
  return <AnimationClockProvider value={clock}><CadFileViewSurface {...props} /></AnimationClockProvider>;
}


function CadFileViewSurface({
  client, entry, serverInfo, renderSession, preferences, onPreferenceChange, onOpenFile, className = "",
  panelSlot, colorScheme = "light", selectReference, onReference, onCapture, captureRequest,
  openPanel = "", onPanelOpen, onChromeVisibilityChange, onActivityChange, state, onStateChange
}) {
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
  const tips = {
    seen: Array.isArray(preferences.seenTips) ? preferences.seenTips : [],
    dismiss: (id) => onPreferenceChange({ seenTips: [...new Set([...(preferences.seenTips || []), id])] })
  };
  const hostLayoutMode = CAD_WORKSPACE_LAYOUT_MODE.DESKTOP;
  const hostSheetWidth = null;
  const hostPanelSlot = panelSlot;
  const drawsOwnPanelColumn = false;
  const themeEditing = openPanel === CAD_PANEL.theme;
  const tabToolsOpen = openPanel === CAD_PANEL.fileSheet;
  const filesPanelOpen = openPanel === "tree";
  const panelRef = useRef({ openPanel, onPanelOpen });
  panelRef.current = { openPanel, onPanelOpen };
  const setFilesPanelOpen = useCallback((value) => {
    const current = panelRef.current.openPanel === "tree";
    const next = typeof value === "function" ? value(current) : value;
    if (next !== current) panelRef.current.onPanelOpen?.(next ? "tree" : "");
  }, []);
  const setThemeEditing = useCallback((value) => {
    const current = panelRef.current.openPanel === CAD_PANEL.theme;
    const next = typeof value === "function" ? value(current) : value;
    if (next !== current) panelRef.current.onPanelOpen?.(next ? CAD_PANEL.theme : "");
  }, []);
  const setTabToolsOpen = useCallback((value) => {
    const current = panelRef.current.openPanel === CAD_PANEL.fileSheet;
    const next = typeof value === "function" ? value(current) : value;
    if (next !== current) panelRef.current.onPanelOpen?.(next ? CAD_PANEL.fileSheet : "");
  }, []);
  const resolvedColorSchemeMode = colorScheme === "dark" ? "dark" : "light";
  const uiPrefersDark = resolvedColorSchemeMode === "dark";
  const themeReadOptions = useMemo(() => ({ prefersDark: uiPrefersDark }), [uiPrefersDark]);
  const storeSnapshot = useSyncExternalStore(client.subscribe, client.getSnapshot, client.getSnapshot);
  const selectedKey = fileKey(entry);
  const liveEntry = storeSnapshot.entries.find((item) => fileKey(item) === selectedKey) || entry;
  const manifestRevision = storeSnapshot.revision;
  const explicitFileParam = cadFileParamForEntry(entry);
  const viewerServerInfo = serverInfo;
  const viewerServerBackend = String(viewerServerInfo?.backend || "").trim().toLowerCase();
  const [fileSheetOpenSectionIds, setFileSheetOpenSectionIds] = useState(null);
  const [dxfThicknessMm, setDxfThicknessMm] = useState(0);
  const [dxfBendSettings, setDxfBendSettings] = useState([]);
  const [dxfViewMode, setDxfViewMode] = useState("2d");
  const [referenceQuery, setReferenceQuery] = useState("");
  const [selectedReferenceIds, setSelectedReferenceIds] = useState([]);
  const [largeFileState, setLargeFileState] = useState(() => normalizeLargeFileState(DEFAULT_LARGE_FILE_STATE));
  const [hoveredListReferenceId, setHoveredListReferenceId] = useState("");
  const [hoveredModelReferenceId, setHoveredModelReferenceId] = useState("");
  const [selectedPartIds, setSelectedPartIds] = useState([]);
  const [selectedRenderPartIdByAssemblyPartId, setSelectedRenderPartIdByAssemblyPartId] = useState({});
  const [selectedWholeEntryCadRefToken, setSelectedWholeEntryCadRefToken] = useState("");
  const [expandedStepTreeNodeIds, setExpandedStepTreeNodeIds] = useState([]);
  const [activeTreeNodeScrollKey, setActiveTreeNodeScrollKey] = useState("");
  const [hiddenPartIds, setHiddenPartIds] = useState([]);
  const [isolatedAssemblyNodeIds, setIsolatedAssemblyNodeIds] = useState([]);
  const [viewerContextMenu, setViewerContextMenu] = useState(null);
  const [displaySettings, setDisplaySettings] = useState(() => normalizeDisplaySettings());
  const [hoveredListPartId, setHoveredListPartId] = useState("");
  const [hoveredModelPartId, setHoveredModelPartId] = useState("");
  const [copyStatus, setCopyStatus] = useState("");
  const [stepUpdateInProgress, setStepUpdateInProgress] = useState(false);
  const [screenshotStatus, setScreenshotStatus] = useState("");
  const [persistenceStatus, setPersistenceStatus] = useState("");
  const [viewerLayoutMode, setViewerLayoutMode] = useState(readViewerLayoutMode);
  const [layoutViewportWidth, setLayoutViewportWidth] = useState(readViewerViewportWidth);
  const isDesktop = hostLayoutMode === CAD_WORKSPACE_LAYOUT_MODE.DESKTOP ||
    viewerLayoutMode === CAD_WORKSPACE_LAYOUT_MODE.DESKTOP;
  const [viewerAlertOpen, setViewerAlertOpen] = useState(false);
  const [viewerRuntimeAlert, setViewerRuntimeAlert] = useState(null);
  // One active theme id plus at most one custom settings blob. Presets are
  // read-only; editing anything moves the active theme to "custom".
  const [themeState, setThemeState] = useState(() => createThemeState(preferences.theme?.themeId, preferences.theme?.custom, themeReadOptions));
  // A host that flips light/dark re-resolves the "system" preset; the
  // standalone app's document never changes scheme under it.
  const themeReadOptionsRef = useRef(themeReadOptions);
  useEffect(() => {
    if (themeReadOptionsRef.current === themeReadOptions) {
      return;
    }
    themeReadOptionsRef.current = themeReadOptions;
    setThemeState((current) => createThemeState(current.themeId, current.custom, themeReadOptions));
  }, [themeReadOptions]);
  const themeSettings = themeState.settings;
  const themeId = themeState.themeId;
  // What the "System" theme paints the scene on: the chrome's `--background`,
  // or the written-out pair where there is no chrome (chromeBackdrop.js).
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
  // The package's parsed contours, fetched once per entry and kept by URL. Curved bends
  // re-mesh from these; the URL carries the package version, so a rebuild refetches.
  const drawingGeometryCacheRef = useRef(new Map());
  const [drawingGeometry, setDrawingGeometry] = useState(null);
  const resolvedThemeSettings = useMemo(
    () => resolveCadThemeSettings(themeSettings, themeId, { prefersDark: uiPrefersDark, chromeBackdropColor }),
    [chromeBackdropColor, themeId, themeSettings, uiPrefersDark]
  );
  // The colour behind the canvas, which is the scene's own at its edges.
  const sceneBackdrop = useMemo(
    () => sceneBackdropEdgeColor(resolvedThemeSettings.background, chromeBackdropColor),
    [chromeBackdropColor, resolvedThemeSettings]
  );
  const resolvedDisplayEdgeSettings = useMemo(() => {
    // Edge theme — colour, opacity, thickness — is fixed, not a user
    // setting. It comes from the @hardcore/core defaults, or from a theme that styles its
    // own linework (e.g. Terminal's neon-green outline). Whether edges draw at
    // all is still decided by the display MODE, not here.
    //
    // Persisted per-file edge settings written by an older build are ignored
    // rather than merged: with the controls gone they could never be changed
    // back, so a stale value would be stuck forever.
    const themeEdges = resolvedThemeSettings.edges;
    if (themeEdges && themeEdges.enabled === true) {
      return normalizeDisplayEdgeSettings(themeEdges);
    }
    return normalizeDisplayEdgeSettings();
  }, [resolvedThemeSettings]);
  const updateDisplaySettings = useCallback((nextValue) => {
    setDisplaySettings((current) => normalizeDisplaySettings(
      typeof nextValue === "function" ? nextValue(current) : nextValue
    ));
  }, []);
  const [previewMode, setPreviewMode] = useState(false);
  useEffect(() => { onChromeVisibilityChange?.(!previewMode); }, [onChromeVisibilityChange, previewMode]);
  const tabToolsWidth = 365;
  const [drawingTool, setDrawingTool] = useState(DRAWING_TOOL.FREEHAND);
  const [viewerPerspective, setViewerPerspective] = useState(null);
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
  const [stepModuleEnabled, setStepModuleEnabled] = useState(true);
  // The ANIMATION system, loaded and held entirely apart from the kinematics
  // state above: kinematics is the sidecar's, choreography is the render
  // module beside the document (<name>.step.js), and a model may ship either,
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
    applyComponentLodPayload,
    meshLoadInProgress,
    meshLoadTargetFile,
    meshLoadStage,
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
    urdfLoadStage,
    urdfLoadProgress,
    referenceState,
    setReferenceState,
    referenceStatus,
    setReferenceStatus,
    setReferenceError,
    referenceLoadStage,
    displayEdgeState,
    setDisplayEdgeState,
    setDisplayEdgeStatus,
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
    tessellationCache: renderSession.tessellationCache,
    entryHasMesh,
    entryHasReferences,
    entryHasDisplayEdges,
    buildNormalizedReferenceState,
  });

  const catalogSelectedEntry = liveEntry;
  const fileParamSelectionPending = false;
  const missingFileRef = "";
  const catalogSelectedEntrySourceFormat = entrySourceFormat(catalogSelectedEntry);
  // Unified render-artifact status for the selected entry: ready (render) | generating (loading) |
  // error (fatal). A missing/stale cache is not an issue — it just triggers a (re)build. Replaces
  // the per-entry step-source-status fetch, the mesh-stripping merge, and the build effect.
  // Every artifact-managed kind: STEP models and DXF drawings (generated `.dxf.py` AND
  // imported `.dxf` alike). An imported `.dxf` used to be excluded because it
  // "renders directly from disk" -- true only while the client still parsed and extruded DXF
  // entities in the browser. It renders from the package's baked preview.glb now, so it needs
  // the build for exactly the reason a generated one does.
  const selectedArtifact = useArtifact(
    catalogSelectedEntry ? fileKey(catalogSelectedEntry) : "",
    {
      enabled: isArtifactManagedFormat(catalogSelectedEntrySourceFormat),
      freshnessKey: `${catalogSelectedEntry?.hash || ""}:${manifestRevision}`,
      client,
    }
  );
  const selectedArtifactGenerating = selectedArtifact.status === "compiling";
  // The in-flight build's own report of where it is (null until it reports, and for
  // every loading state that is not an artifact build). Only meaningful while
  // generating — a stale frame must not outlive the build that produced it.
  const selectedArtifactProgress = selectedArtifactGenerating ? selectedArtifact.progress : null;
  // What the loading overlay reports. A model being BUILT reports through the artifact
  // pipeline; a robot has no build behind it at all — it is a URDF plus a pile of meshes —
  // and its loader's own mesh count is then the only progress in existence. The two are
  // mutually exclusive in practice, and normalizing both through one function is what keeps
  // the overlay from having to know which subsystem it is looking at.
  const selectedLoadProgress =
    selectedArtifactProgress || normalizeArtifactProgress(urdfLoadProgress);
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
      const base = !catalogSelectedEntry || selectedArtifact.status === "rendered"
        ? catalogSelectedEntry
        : entryWithoutRenderAssets(catalogSelectedEntry);
      if (!base) {
        return base;
      }
      const fileRefPrefix = fileRefPrefixByPath.get(cadFileParamForEntry(base)) || "";
      return fileRefPrefix ? { ...base, fileRefPrefix } : base;
    },
    [catalogSelectedEntry, selectedArtifact.status, fileRefPrefixByPath]
  );
  // Cache states never become user-facing "issues"; only a fatal build/source failure does.
  const selectedStepSourceStatus = selectedArtifact.status === "failed"
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
  const selectedStepModuleUrl = supportsSidecarParams ? entryPoseUrl(selectedEntry) : "";
  const selectedStepModuleCadPath = selectedStepModuleUrl ? cadPathForEntry(selectedEntry) : "";
  const selectedStepModuleDefinition = stepModuleLoadState.url === selectedStepModuleUrl
    ? stepModuleLoadState.definition
    : null;
  const selectedRenderModuleUrl = supportsSidecarParams ? entryRenderModuleUrl(selectedEntry) : "";
  const selectedAnimationClips = animationLoadState.url === selectedRenderModuleUrl
    ? animationLoadState.clips
    : null;
  const selectedAnimationStatus = selectedRenderModuleUrl
    ? (animationLoadState.url === selectedRenderModuleUrl ? animationLoadState.status : "loading")
    : "idle";
  const selectedAnimationLoadError = animationLoadState.url === selectedRenderModuleUrl
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
    selectedMeshMatches &&
    !!meshState?.assemblyBackgroundError;
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
      setStepModuleEnabled(true);
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
    setStepModuleEnabled(true);

    loadKinematicsModuleDefinition(selectedStepModuleUrl, {
      signal: controller.signal,
      cadPath: selectedStepModuleCadPath
    }).then((definition) => {
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
      setStepModuleEnabled(resolved.enabled);
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
      setStepModuleEnabled(true);
    });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [fileSessionNamespace, selectedEntry, selectedStepModuleCadPath, selectedStepModuleUrl]);

  // The animation half of the same sidecar, loaded on its own: the copied
  // .anim.js text compiles to clips through a Blob import. A model with no
  // animation section resolves to no clips and no Animation tab, and a broken
  // one reports its own error without disturbing the Pose tab.
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    const resetAnimation = () => {
      const nextState = buildDefaultAnimationState();
      animationStateRef.current = nextState;
      setAnimationState(nextState);
      resetAnimationClock();
    };

    if (!selectedRenderModuleUrl) {
      setAnimationLoadState({ url: "", status: "idle", error: "", clips: null });
      resetAnimation();
      return () => {
        cancelled = true;
        controller.abort();
      };
    }

    setAnimationLoadState({
      url: selectedRenderModuleUrl,
      status: "loading",
      error: "",
      clips: null
    });
    resetAnimation();

    loadRenderModule(selectedRenderModuleUrl, { signal: controller.signal })
      .then((renderModule) => {
        if (cancelled) {
          return;
        }
        const clips = renderModule?.clips || {};
        setAnimationLoadState({
          url: selectedRenderModuleUrl,
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
          url: selectedRenderModuleUrl,
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
  }, [fileSessionNamespace, selectedEntry, selectedRenderModuleUrl]);

  const selectedUrdfMeshGeometryResult = useMemo(() => {
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
        selectedUrdfJointValues
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
  }, [selectedUrdfData, selectedUrdfJointValues, selectedUrdfMeshGeometryResult]);
  const selectedMeshData = selectedEntryContentKind === VIEWPORT_CONTENT.ROBOT
    ? selectedUrdfPreview.meshData
    : selectedMeshMatches
      ? meshState.meshData
      : null;
  const selectedAnimationClipList = useMemo(
    () => animationClipList(selectedAnimationClips),
    [selectedAnimationClips]
  );
  const selectedActiveAnimationClip = useMemo(
    () => findAnimationClip(selectedAnimationClips, animationState.activeClipId),
    [selectedAnimationClips, animationState.activeClipId]
  );
  const selectedStepParameterRuntime = useMemo(() => {
    if (!selectedStepModuleDefinition || !stepModuleEnabled) {
      return null;
    }
    return {
      definition: selectedStepModuleDefinition,
      parameterValues: normalizeStepModuleParameterValues(selectedStepModuleDefinition, stepModuleParameterValues),
      cadPath: selectedStepModuleDefinition.cadPath || selectedStepModuleCadPath,
      sourceUrl: selectedStepModuleUrl
    };
  }, [
    selectedStepModuleCadPath,
    selectedStepModuleDefinition,
    selectedStepModuleUrl,
    stepModuleEnabled,
    stepModuleParameterValues
  ]);
  // What the viewport needs to draw one animated frame: the compiled clip and a
  // time. The render pane swaps in the live clock while playing; everything else
  // about playback stays out of the render path.
  //
  // The Animation section's gate expresses itself HERE and nowhere else, mirroring
  // the pose gate above: switched off this memo is null, and null is already how
  // the viewport draws the rest scene — pose only, evaluator never run. So there
  // is no "disabled" render path, only the absence of a frame.
  const selectedAnimationRuntime = useMemo(() => animationRenderFrame({
    enabled: animationState.enabled !== false,
    clip: selectedActiveAnimationClip,
    elapsedSec: animationState.elapsedSec,
    playing: animationState.playing
  }), [
    animationState.elapsedSec,
    animationState.enabled,
    animationState.playing,
    selectedActiveAnimationClip
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

  const handleStepModuleParameterChange = useCallback((parameterId, value) => {
    const id = String(parameterId || "").trim();
    const parameter = selectedStepModuleDefinition?.parameterMap?.[id];
    if (!parameter) {
      return;
    }
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
  const handleApplyPose = useCallback((poseName) => {
    if (!selectedStepModuleDefinition) {
      return;
    }
    const nextParameterValues = normalizeStepModuleParameterValues(
      selectedStepModuleDefinition,
      poseValuesForPreset(selectedStepModuleDefinition, poseName)
    );
    stepModuleParameterValuesRef.current = nextParameterValues;
    setStepModuleParameterValues(nextParameterValues);
  }, [selectedStepModuleDefinition]);

  // Turning the mate graph off leaves the model at rest — and leaves any playing
  // clip alone. Animation is not downstream of pose and never stops with it.
  const handleStepModuleEnabledChange = useCallback((enabled) => {
    setStepModuleEnabled(enabled !== false);
  }, []);

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
  // The render module's clips are checked against the compiled tree once it is
  // in hand: a target no part carries fails HERE, in the Status tab, not the
  // first time playback reaches that frame.
  const selectedAnimationValidationError = useMemo(() => {
    if (!selectedAnimationClips || !Array.isArray(selectedMeshData?.parts) || !selectedMeshData.parts.length) {
      return "";
    }
    return validateRenderModuleClips(THREE, selectedMeshData, selectedAnimationClips)
      .map((problem) => `${problem.clip}: ${problem.error}`)
      .join("\n");
  }, [selectedAnimationClips, selectedMeshData]);
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
      await copyTextToClipboard(buildParameterValuesCopyText(runtime.definition, runtime.values));
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
      const clipboardText = await readTextFromClipboard();
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
  const stepTreeRoot = useMemo(() => {
    if (!supportsParts) {
      return null;
    }
    return buildStepTreeRoot({
      selectedEntry,
      assemblyRoot,
      meshData: selectedMeshData
    });
  }, [assemblyRoot, supportsParts, selectedEntry, selectedMeshData]);
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
  const requestedStepTreeTopologyNodeIds = useMemo(() => {
    if (!supportsTopology || !isAssemblyView || !selectedEntryHasReferences) {
      return [];
    }
    return uniqueStringList(
      expandedStepTreeNodeIds
        .map((id) => String(id || "").trim())
        .filter((id) => id && loadableStepTreeTopologyNodeIdSet.has(id))
    );
  }, [
    expandedStepTreeNodeIds,
    isAssemblyView,
    supportsTopology,
    loadableStepTreeTopologyNodeIdSet,
    selectedEntryHasReferences
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
      ? viewerSelectableAssemblyNodeIds
        .map((nodeId) => findAssemblyNode(assemblyRoot, nodeId))
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
    selectedArtifact.status === "failed";
  const meshViewerLoading =
    !!selectedEntry &&
    // A DRAWING has no flat pattern and bakes nothing, so "no mesh yet" is its finished state,
    // not a pending one. Waiting on the mesh path left the pane on LOADING forever (issue #246).
    !selectedEntryIsDrawingDocument &&
    (selectedStepArtifactRenderPending || !artifactBlocksRender) &&
    status !== ASSET_STATUS.ERROR &&
    (!selectedMeshMatches || status === ASSET_STATUS.LOADING || selectedStepModuleLoading);
  // DXF has no arm -- it renders its baked preview through the mesh path like everything
  // else.
  const viewerLoading = {
    [ASSET_KIND.ROBOT]: urdfViewerLoading,
    [ASSET_KIND.MESH]: meshViewerLoading,
    // A DXF loads a drawing but RENDERS the drawing package's baked preview through the
    // mesh path, so its readiness is the mesh loader's.
    [ASSET_KIND.DRAWING]: meshViewerLoading
  }[assetKindForRenderFormat(effectiveRenderFormat)];
  const effectiveViewerLoading = viewerLoading || selectedArtifactGenerating || fileParamSelectionPending;
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
  const assemblyHydrationLoading =
    isAssemblyView &&
    selectedMeshMatches &&
    selectedAssemblyStructureReady &&
    !selectedAssemblyInteractionReady &&
    !selectedAssemblyHydrationFailed;
  // Six format arms said one thing: name the asset being fetched. Formats the viewer does
  // not build ARE their own asset, so the label is just their name; artifact-managed ones
  // fall through to the build/parameter progression below, which is about the package
  // rather than the file.
  // A robot assembles from many meshes and the loader already counts them off. Reporting
  // "loading meshes 7/13" instead of a static card is the difference between a 15-second
  // wait that looks like progress and one that looks like a hang; the count was already
  // computed and only ever reached the file-list chip.
  const robotLoadingLabel = `Loading ${renderFormatLabel(effectiveRenderFormat)} robot...`;
  const simpleLoadingLabel = selectedArtifactGenerating || isArtifactManagedFormat(effectiveRenderFormat)
    ? ""
    : {
        [ASSET_KIND.ROBOT]: urdfLoadStage
          ? `${capitalizeFirst(urdfLoadStage)}...`
          : robotLoadingLabel,
        [ASSET_KIND.MESH]: `Loading ${renderFormatLabel(effectiveRenderFormat)}...`,
        [ASSET_KIND.DRAWING]: ""
      }[assetKindForRenderFormat(effectiveRenderFormat)];
  const viewerLoadingLabel = selectedArtifactGenerating
    ? "Generating file..."
    : simpleLoadingLabel
      ? simpleLoadingLabel
      : stepUpdateInProgress
                ? ARTIFACT_GENERATING_LABEL
                : selectedStepArtifactRenderPending
                  ? ARTIFACT_GENERATING_LABEL
                  : selectedStepModuleLoading
                    ? "Loading STEP module..."
                  : selectedEntry && !selectedEntryHasMesh
                    ? ARTIFACT_GENERATING_LABEL
                    : "Loading CAD...";
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

  const viewerAlert = useMemo(() => {
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
      ) || viewerRuntimeAlert;
    }
    const meshAlert = buildViewerMeshAlert(
      selectedEntry,
      !!selectedMeshData,
      status === ASSET_STATUS.ERROR ? error : "",
      selectedArtifact
    );
    return meshAlert || viewerRuntimeAlert;
  }, [
    effectiveRenderFormat,
    error,
    selectedEntry,
    selectedArtifact,
    selectedArtifactGenerating,
    selectedMeshData,
    selectedUrdfPreviewError,
    status,
    urdfError,
    urdfStatus,
    viewerLoading,
    viewerRuntimeAlert
  ]);
  const viewerAlertKey = viewerAlert
    ? [
      fileKey(selectedEntry),
      viewerAlert.severity,
      viewerAlert.summary,
      viewerAlert.title
    ].join(":")
    : "";
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
  // Viewport LOD (design/unified-tessellation.md Phase 5): camera-settle
  // driven re-tessellation of the components that project the worst error.
  const { onCameraMoved: onLodCameraMoved } = useViewportLod({
    viewerRef,
    lodPackage,
    applyComponentLodPayload,
    tessellationCache: renderSession.tessellationCache
  });
  const previewUiStateRef = useRef(null);
  const fileSessionSaveTimerRef = useRef(0);
  const activePerspectiveRef = useRef(null);
  const selectedFileSheetKeyRef = useRef("");

  const desktopRightPanelOpen = false;

  // Selecting a preset (or System) is the only "reset": it swaps the active
  // theme wholesale. The custom slot is kept so the user can flip back to it.
  const selectTheme = useCallback((nextThemeId) => {
    setThemeState((current) => createThemeState(nextThemeId, current.custom, themeReadOptions));
  }, [themeReadOptions]);

  // Any settings edit lands in the single custom slot and makes it active,
  // unless it happens to reproduce a preset exactly.
  const updateThemeSettings = useCallback((updater) => {
    setThemeState((current) => {
      const next = typeof updater === "function" ? updater(current.settings) : updater;
      const settings = normalizeThemeSettings(next);
      const matchingPresetId = getThemePresetIdForSettings(settings);
      return {
        themeId: matchingPresetId || CUSTOM_THEME_ID,
        custom: matchingPresetId ? current.custom : settings,
        settings
      };
    });
  }, [handlePersistenceWriteError]);

  // The theme sidebar and the file sheet are mutually exclusive. Opening one
  // closes the other outright — rather than merely hiding it behind the new
  // panel — so that closing the panel you opened leaves nothing open, and the
  // other sidebar has to be reopened deliberately.
  const closeThemeEditor = useCallback(() => {
    setThemeEditing(false);
  }, []);

  useEffect(() => {
    onPreferenceChange({ theme: { themeId: themeState.themeId, custom: themeState.custom } });
  }, [themeState, onPreferenceChange]);
  useEffect(() => {
    setThemeState((current) => JSON.stringify({ themeId: current.themeId, custom: current.custom }) === JSON.stringify(preferences.theme)
      ? current : createThemeState(preferences.theme?.themeId, preferences.theme?.custom, themeReadOptions));
  }, [preferences.theme, themeReadOptions]);

  const drawingSettingsLoadedKeyRef = useRef(null);
  useEffect(() => {
    if (drawingSettingsLoadedKeyRef.current !== selectedKey || !selectedEntryIsDrawing) return;
    emitState({ drawing: { thicknessMm: drawingThicknessMm, bends: drawingBends,
      bendStyle: drawingBendStyle, bendRadiusMm: drawingBendRadiusMm, kFactor: drawingKFactor,
      hiddenLayers: drawingHiddenLayers, units: drawingUnits, orientation: drawingOrientation,
      material: drawingMaterial, viewMode: drawingViewMode } });
  }, [selectedKey, selectedEntryIsDrawing, drawingThicknessMm, drawingBends, drawingBendStyle,
    drawingBendRadiusMm, drawingKFactor, drawingHiddenLayers, drawingUnits, drawingOrientation,
    drawingMaterial, drawingViewMode, emitState]);
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
    loadRenderDxf(drawingGeometryUrl)
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
      (selectedRenderModuleUrl && selectedAnimationStatus === "loading") ||
      selectedAnimationError
    ),
    hasFileStatus: selectedFileHasWarningOrErrorStatus,
    hasDxfBendsPanel: selectedFileSheetKind === "dxf" && drawingBends.length > 0,
    hasDxfLayersPanel: selectedFileSheetKind === "dxf" && drawingLayers.length > 1,
    isSdf: selectedFileSheetKind === "sdf",
    showJoints: selectedFileSheetKind === "urdf" || selectedFileSheetKind === "srdf" || selectedFileSheetKind === "sdf"
  }), [
    selectedAnimationClipList,
    selectedAnimationError,
    selectedAnimationStatus,
    selectedFileSheetKind,
    selectedFileHasWarningOrErrorStatus,
    selectedStepModuleDefinition,
    selectedStepModuleError,
    selectedStepModuleStatus,
    selectedStepModuleUrl,
    drawingBends,
    drawingLayers
  ]);

  const renderedSelectedFileSheetSectionIds = useMemo(
    () => renderedFileSheetSectionIds(selectedFileSheetKind, fileSheetSectionOptions),
    [fileSheetSectionOptions, selectedFileSheetKind]
  );
  const defaultSelectedFileSheetOpenSectionIds = useMemo(
    () => defaultOpenFileSheetSectionIds(selectedFileSheetKind, fileSheetSectionOptions),
    [fileSheetSectionOptions, selectedFileSheetKind]
  );
  const effectiveFileSheetOpenSectionIds = useMemo(() => (
    normalizeFileSheetOpenSectionIds(
      Array.isArray(fileSheetOpenSectionIds)
        ? fileSheetOpenSectionIds
        : defaultSelectedFileSheetOpenSectionIds,
      renderedSelectedFileSheetSectionIds
    )
  ), [
    defaultSelectedFileSheetOpenSectionIds,
    fileSheetOpenSectionIds,
    renderedSelectedFileSheetSectionIds
  ]);

  const handleFileSheetOpenSectionIdsChange = useCallback((nextSectionIds) => {
    setFileSheetOpenSectionIds(
      normalizeFileSheetOpenSectionIds(nextSectionIds, renderedSelectedFileSheetSectionIds)
    );
  }, [renderedSelectedFileSheetSectionIds]);

  const openFileSheetSection = useCallback((sectionId, { openSheet = true } = {}) => {
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
      if (baseSectionIds.includes(normalizedSectionId)) {
        return baseSectionIds;
      }
      return normalizeFileSheetOpenSectionIds(
        [...baseSectionIds, normalizedSectionId],
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
      renderedSelectedFileSheetSectionIds
    );
    if (orderedStringListEqual(normalizedSectionIds, fileSheetOpenSectionIds)) {
      return;
    }
    setFileSheetOpenSectionIds(normalizedSectionIds);
  }, [fileSheetOpenSectionIds, renderedSelectedFileSheetSectionIds]);

  useEffect(() => {
    if (selectedFileStatusLevel !== FILE_STATUS_LEVELS.ERROR) {
      return;
    }
    setFileSheetOpenSectionIds((current) => {
      const baseSectionIds = normalizeFileSheetOpenSectionIds(
        Array.isArray(current) ? current : defaultSelectedFileSheetOpenSectionIds,
        renderedSelectedFileSheetSectionIds
      );
      const nextSectionIds = fileSheetSectionIdsWithOpenSection(
        baseSectionIds,
        renderedSelectedFileSheetSectionIds,
        FILE_SHEET_SECTION_IDS.FILE_STATUS
      );
      return orderedStringListEqual(nextSectionIds, baseSectionIds) ? current : nextSectionIds;
    });
  }, [
    defaultSelectedFileSheetOpenSectionIds,
    renderedSelectedFileSheetSectionIds,
    selectedFileStatusLevel,
    selectedKey
  ]);

  const buildActiveTabSnapshot = useCallback(() => {
    return cloneTabSnapshot({
      referenceQuery,
      selectedReferenceIds,
      selectedPartIds,
      inspectedAssemblyNodeId: "",
      expandedStepTreeNodeIds,
      fileSheetOpenSectionIds: effectiveFileSheetOpenSectionIds,
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
    effectiveFileSheetOpenSectionIds,
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
    // While a clip plays the authoritative time is the clock store's, not React
    // state's — the loop only writes back when playback stops.
    const snapshotAnimationElapsedSec = animationState.playing
      ? getAnimationClock()
      : animationState.elapsedSec;
    return createFileSessionSnapshot({
      fileKey: targetFileKey,
      entry: targetEntry,
      slices: {
        ...(entrySourceFormat(targetEntry) === RENDER_FORMAT.STEP ? { display: displaySettings } : {}),
        tab: buildActiveTabSnapshot(),
        stepModule: {
          enabled: stepModuleEnabled,
          parameterValues: stepModuleParameterValues
        },
        animation: {
          activeClipId: animationState.activeClipId,
          enabled: animationState.enabled,
          elapsedSec: snapshotAnimationElapsedSec,
          speed: animationState.speed,
          loopEnabled: animationState.loopEnabled
        },
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
    selectedEntry,
    stepModuleEnabled,
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
    setDisplaySettings(
      entrySourceFormat(entry) === RENDER_FORMAT.STEP
        ? normalizeDisplaySettings(sessionState?.slices?.display)
        : normalizeDisplaySettings()
    );

    const stepModuleSlice = sessionState?.slices?.stepModule || null;
    if (stepModuleSlice) {
      setStepModuleEnabled(stepModuleSlice.enabled !== false);
      setStepModuleParameterValues(stepModuleSlice.parameterValues || {});
    }

    // The animation slice restores against the CLIPS this model actually
    // compiled, which is why it is resolved through restoreAnimationState rather
    // than trusted as stored.
    const animationSlice = sessionState?.slices?.animation || null;
    if (animationSlice) {
      const restoredAnimationState = restoreAnimationState(
        animationSlice,
        animationLoadState.url === entryRenderModuleUrl(entry) ? animationLoadState.clips : null
      );
      animationStateRef.current = restoredAnimationState;
      setAnimationState(restoredAnimationState);
      setAnimationClock(restoredAnimationState.elapsedSec);
    }

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
  }, [animationLoadState, entryMap, readEntrySessionState]);

  const fileSheetSelectionKeyForTab = useCallback((key) => {
    const normalizedKey = String(key || "").trim();
    const fileSheetKind = fileSheetKindForEntry(entryMap.get(normalizedKey));
    return normalizedKey && fileSheetKind ? `${normalizedKey}:${fileSheetKind}` : "";
  }, [entryMap]);

  const applyTabRecord = useCallback((tabRecord) => {
    const nextTab = createTabRecord(tabRecord?.key || "", tabRecord || {});
    const nextPerspective = clonePerspectiveSnapshot(nextTab.camera);
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

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }
    const handlePageHide = () => {
      flushActiveFileSession();
    };
    window.addEventListener("pagehide", handlePageHide);
    return () => {
      window.removeEventListener("pagehide", handlePageHide);
    };
  }, [flushActiveFileSession]);

  useEffect(() => {
    selectedReferenceIdsRef.current = selectedReferenceIds;
  }, [selectedReferenceIds]);

  useEffect(() => {
    selectedPartIdsRef.current = selectedPartIds;
  }, [selectedPartIds]);

  useEffect(() => {
    if (!focusedAssemblyNodeIds.length || !selectedPartIds.length) {
      return;
    }
    const focusedNodeIdSet = new Set(focusedAssemblyNodeIds);
    const nextSelectedPartIds = selectedPartIds.filter((id) => !focusedNodeIdSet.has(String(id || "").trim()));
    if (nextSelectedPartIds.length === selectedPartIds.length) {
      return;
    }
    selectedPartIdsRef.current = nextSelectedPartIds;
    setSelectedPartIds(nextSelectedPartIds);
    setSelectedRenderPartIdByAssemblyPartId((current) => {
      const selectedNodeIdSet = new Set(nextSelectedPartIds);
      const nextMap = {};
      for (const [nodeId, renderPartId] of Object.entries(current || {})) {
        if (selectedNodeIdSet.has(nodeId)) {
          nextMap[nodeId] = renderPartId;
        }
      }
      return nextMap;
    });
    setCopyStatus("");
  }, [focusedAssemblyNodeIds, selectedPartIds]);

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
    if (selectedMeshMatches && status !== ASSET_STATUS.LOADING) {
      setStepUpdateInProgress(false);
    }
  }, [selectedEntry, selectedMeshMatches, status, stepUpdateInProgress]);

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
    setViewerAlertOpen(false);
  }, [viewerAlertKey]);

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
    if (meshLoadInProgress && meshLoadTargetFile === fileKey(selectedEntry)) {
      return;
    }
    if (
      selectedMeshMatches &&
      (
        !isAssemblyView ||
        selectedAssemblyInteractionReady ||
        selectedAssemblyHydrationFailed
      )
    ) {
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
    (referenceState.loadedTopologyKey || "*") === requestedTopologyKey;
  const selectedSelectorRuntime = selectedReferencesMatch ? referenceState?.selectorRuntime || null : null;
  const selectedDisplayEdgesMatch =
    !!displayEdgeState &&
    !!selectedEntry &&
    selectedEntryHasDisplayEdges &&
    displayEdgeState.fileRef === fileKey(selectedEntry) &&
    displayEdgeState.displayEdgeHash === entryAssetHash(selectedEntry, "displayEdgeTopology");
  const selectedDisplayEdgeRuntime = selectedDisplayEdgesMatch ? displayEdgeState?.displayEdgeRuntime || null : null;
  const selectedStepPartRootActive = !isAssemblyView && selectedPartIds.includes(STEP_MODEL_ROOT_ID);
  const plainStepReferencePickingEnabled =
    effectiveRenderFormat === RENDER_FORMAT.STEP &&
    selectedEntryHasReferences &&
    !isAssemblyView;
  const assemblyStepTreeTopologyLoadingEnabled =
    effectiveRenderFormat === RENDER_FORMAT.STEP &&
    selectedEntryHasReferences &&
    isAssemblyView &&
    requestedStepTreeTopologyNodeIds.length > 0;
  const selectedStepDisplayEdgesRequested =
    effectiveRenderFormat === RENDER_FORMAT.STEP &&
    selectedEntryHasDisplayEdges &&
    !displayModeIsWireframe(displaySettings.mode) &&
    (displayModeForcesEdges(displaySettings.mode) || resolvedDisplayEdgeSettings.enabled !== false);
  const selectedTopologyExplicitlyEnabled = largeFileState.selectableTopologyEnabled === true;
  const selectedTopologyLargeByCost = Boolean(
    isLargeStepGlbEntry(selectedEntry) ||
    (selectedMeshMatches && isLargeMeshData(selectedMeshData))
  );
  const selectedTopologyWaitingForMeshCost = Boolean(
    plainStepReferencePickingEnabled &&
    !hasStepGlbByteCost(selectedEntry) &&
    !selectedMeshMatches
  );
  const referenceLoadingExplicitlyRequested = selectedStepPartRootActive;
  const selectedTopologyDeferredByCost = Boolean(
    plainStepReferencePickingEnabled &&
    selectedTopologyLargeByCost &&
    !selectedTopologyExplicitlyEnabled &&
    !referenceLoadingExplicitlyRequested
  );
  const topLevelReferenceSelectionActive =
    selectedStepPartRootActive ||
    plainStepReferencePickingEnabled;
  const referenceLoadingEnabled =
    selectedStepPartRootActive ||
    assemblyStepTreeTopologyLoadingEnabled ||
    (
      plainStepReferencePickingEnabled &&
      !selectedTopologyDeferredByCost &&
      !selectedTopologyWaitingForMeshCost
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
      if (
        filtered.length === 1 &&
        filtered[0] === rootId &&
        !selectedPartIdsRef.current.length &&
        !selectedReferenceIdsRef.current.length
      ) {
        return [];
      }
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
    return parseAssemblyPartReferenceSelectionId(reference?.id)?.partId || "";
  }, []);

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
  const visibleStepTreeTopologyReferenceIds = useMemo(() => (
    supportsTopology && isAssemblyView
      ? visibleStepTreeTopologyReferenceIdsForWorkspace(displayStepTreeRoot, expandedStepTreeNodeIds, {
        isAssemblyView
      })
      : []
  ), [
    displayStepTreeRoot,
    expandedStepTreeNodeIds,
    isAssemblyView,
    supportsTopology
  ]);
  const visibleStepTreeTopologyReferenceIdSet = useMemo(
    () => new Set(visibleStepTreeTopologyReferenceIds),
    [visibleStepTreeTopologyReferenceIds]
  );
  const stepTreeCopyReferenceMap = useMemo(
    () => buildStepTreeCopyReferenceMap(displayStepTreeRoot),
    [displayStepTreeRoot]
  );
  const effectiveSelectorRuntime = selectedSelectorRuntime;

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

  useEffect(() => {
    if (!isAssemblyView || !focusedAssemblyNodeIds.length || !selectedReferenceIds.length) {
      return;
    }
    const nextSelectedReferenceIds = selectedReferenceIdsOutsideFocusedAssemblyNodes(
      selectedReferenceIds,
      effectiveActiveReferenceMap,
      focusedAssemblyNodeIds,
      { referencePartId }
    );
    if (orderedStringListEqual(nextSelectedReferenceIds, selectedReferenceIds)) {
      return;
    }
    selectedReferenceIdsRef.current = nextSelectedReferenceIds;
    setSelectedReferenceIds(nextSelectedReferenceIds);
    setCopyStatus("");
  }, [
    effectiveActiveReferenceMap,
    focusedAssemblyNodeIds,
    isAssemblyView,
    referencePartId,
    selectedReferenceIds
  ]);

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
    if (stepModuleTreeSelectionDisabled) {
      return [];
    }
    if (isAssemblyView) {
      if (!visibleStepTreeTopologyReferenceIdSet.size) {
        return [];
      }
      return assemblyStepTreeTopologyReferences.filter((reference) => (
        visibleStepTreeTopologyReferenceIdSet.has(String(reference?.id || "").trim())
      ));
    }
    return effectiveVisibleReferences;
  }, [
    assemblyStepTreeTopologyReferences,
    effectiveVisibleReferences,
    isAssemblyView,
    stepModuleTreeSelectionDisabled,
    visibleStepTreeTopologyReferenceIdSet
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
    !viewerLoading;
  const [measureRulerState, setMeasureRulerState] = useState(null);
  const [activeMeasureId, setActiveMeasureId] = useState("");
  const handleMeasurePick = useCallback((pick) => {
    setMeasureRulerState((current) => applyMeasureRulerPick(current, pick));
  }, []);
  const handleMeasureHoverPoint = useCallback((hover) => {
    setMeasureRulerState((current) => applyMeasureRulerHover(current, hover));
  }, []);
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
  }, [selectedKey]);
  useEffect(() => {
    setMeasureRulerState((current) => measureRulerStateForChange(current, { toolActive: measureModeActive }));
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
    (
      stepUpdateInProgress ||
      referenceSelectionStatus === REFERENCE_STATUS.IDLE ||
      referenceSelectionStatus === REFERENCE_STATUS.LOADING ||
      !effectiveSelectorRuntime
    )
  );
  const filenameLoadActivity = useMemo(() => {
    if (!selectedEntry) {
      return null;
    }

    if (selectedArtifactGenerating) {
      const frame = selectedArtifactProgress ? formatArtifactProgress(selectedArtifactProgress) : null;
      // One number, and only a measured one: a phase's own count. An uncountable phase adds
      // nothing here rather than a percentage of the whole build, which nothing can honestly
      // compute. The phase name and sub-unit live in the tooltip, which is opened on purpose.
      const chip = frame?.determinate ? frame.counts : "";
      return {
        loading: true,
        label: chip ? `${ARTIFACT_GENERATING_LABEL} ${chip}` : ARTIFACT_GENERATING_LABEL,
        title: frame
          ? [frame.label, frame.ordinal && `phase ${frame.ordinal}`, frame.detail]
              .filter(Boolean)
              .join(" — ")
          : "Generator script is running"
      };
    }

    if (isRobotRenderFormat(effectiveRenderFormat) && urdfViewerLoading) {
      return {
        loading: true,
        label: selectedEntryHasUrdf ? (urdfLoadStage || (effectiveRenderFormat === RENDER_FORMAT.SDF ? "loading SDF" : "loading URDF")) : "building",
        title: viewerLoadingLabel
      };
    }

    if (effectiveRenderFormat === RENDER_FORMAT.STEP && stepUpdateInProgress) {
      return {
        loading: true,
        label: ARTIFACT_GENERATING_LABEL,
        title: viewerLoadingLabel
      };
    }

    if (effectiveRenderFormat === RENDER_FORMAT.STEP && selectedStepArtifactRenderPending) {
      return {
        loading: true,
        label: ARTIFACT_GENERATING_LABEL,
        title: viewerLoadingLabel
      };
    }

    if (effectiveRenderFormat === RENDER_FORMAT.STEP && selectedStepModuleLoading) {
      return {
        loading: true,
        label: "loading STEP module",
        title: viewerLoadingLabel
      };
    }

    if ([RENDER_FORMAT.STEP, RENDER_FORMAT.STL, RENDER_FORMAT.THREE_MF, RENDER_FORMAT.GLB].includes(effectiveRenderFormat) && meshViewerLoading) {
      const activeMeshLoadStage = meshLoadTargetFile === fileKey(selectedEntry)
        ? meshLoadStage
        : "";
      return {
        loading: true,
        label: selectedEntryHasMesh ? (activeMeshLoadStage || "loading mesh") : "building",
        title: viewerLoadingLabel
      };
    }

    if (effectiveRenderFormat === RENDER_FORMAT.STEP && assemblyHydrationLoading) {
      const activeMeshLoadStage = meshLoadTargetFile === fileKey(selectedEntry)
        ? meshLoadStage
        : "";
      return {
        loading: true,
        label: activeMeshLoadStage || "loading meshes",
        title: "Loading assembly meshes"
      };
    }

    if (effectiveRenderFormat === RENDER_FORMAT.STEP && referenceSelectionStatus === REFERENCE_STATUS.LOADING) {
      return {
        loading: true,
        label: referenceLoadStage || "loading topology",
        title: "Loading selectable topology"
      };
    }

    if (effectiveRenderFormat === RENDER_FORMAT.STEP && referenceSelectionPending) {
      return {
        loading: true,
        label: "building topology",
        title: "Preparing selectable topology"
      };
    }

    if (assemblySidebarLoading) {
      return {
        loading: true,
        label: "building assembly",
        title: "Preparing assembly parts"
      };
    }

    return null;
  }, [
    assemblyHydrationLoading,
    assemblySidebarLoading,
    effectiveRenderFormat,
    meshLoadStage,
    meshLoadTargetFile,
    referenceLoadStage,
    referenceSelectionPending,
    referenceSelectionStatus,
    selectedEntry,
    selectedEntryHasDxf,
    selectedEntryHasMesh,
    selectedEntryHasUrdf,
    selectedArtifactGenerating,
    selectedArtifactProgress,
    selectedStepArtifactRenderPending,
    selectedStepModuleLoading,
    stepUpdateInProgress,
    meshViewerLoading,
    urdfLoadStage,
    urdfViewerLoading,
    viewerLoadingLabel
  ]);
  useEffect(() => { onActivityChange?.(filenameLoadActivity); }, [filenameLoadActivity, onActivityChange]);
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
      return selectedWholeTopologyReferencePartIds;
    }
    const focusedNodeIdSet = new Set(focusedAssemblyNodeIds);
    return uniqueStringList(
      [
        ...selectedPartIds.flatMap((id) => {
          const normalizedId = String(id || "").trim();
          if (focusedNodeIdSet.has(normalizedId)) {
            return [];
          }
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
    if (
      typeof requestAnimationFrame !== "function" ||
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
    const durationMs = Math.max(toFiniteNumber(options?.durationMs, URDF_JOINT_ANIMATION_DURATION_MS), 1);
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
      await copyTextToClipboard(buildUrdfJointAnglesCopyText(movableUrdfJoints, selectedUrdfJointValues));
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
  const copyReferenceTipActive = canonicalCopySelectionLines.length > 0;
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
    setExpandedStepTreeNodeIds((current) => uniqueStringList([...current, ...idsToExpand]));
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
    setActiveTreeNodeScrollKey(source === "viewer" ? `${Date.now()}:${normalizedNodeId}` : "");
    openFileSheetSection(FILE_SHEET_SECTION_IDS.STEP_TREE, {
      openSheet: shouldOpenFileSheetForSelectionReveal({ isDesktop, source })
    });
    if (expandAncestors || expandSelf) {
      expandStepTreeAroundNode(normalizedNodeId, { expandSelf });
    }
  }, [
    expandStepTreeAroundNode,
    isDesktop,
    openFileSheetSection,
    selectedFileSheetKind
  ]);

  const toggleReferenceSelection = useCallback((referenceId, { multiSelect = false, source = "viewer" } = {}) => {
    if (stepUpdateInProgress || stepModuleTreeSelectionDisabled) {
      return;
    }
    if (source !== "viewer") {
      setActiveTreeNodeScrollKey("");
    }
    const normalizedReferenceId = String(referenceId || "").trim();
    const selectedReference = effectiveActiveReferenceMap.get(normalizedReferenceId);
    const selectedReferenceType = String(selectedReference?.selectorType || "").trim();
    const selectedReferencePartId = referencePartId(selectedReference);
    if (
      isAssemblyView &&
      (selectedReferenceType === "shape" || selectedReferenceType === "occurrence") &&
      selectedReferencePartId &&
      focusedAssemblyNodeIds.includes(selectedReferencePartId)
    ) {
      const nextSelectedReferenceIds = selectedReferenceIdsRef.current
        .filter((id) => String(id || "").trim() !== normalizedReferenceId);
      if (nextSelectedReferenceIds.length !== selectedReferenceIdsRef.current.length) {
        selectedReferenceIdsRef.current = nextSelectedReferenceIds;
        setSelectedReferenceIds(nextSelectedReferenceIds);
        setCopyStatus("");
      }
      return;
    }
    const next = !multiSelect && selectedPartIdsRef.current.length
      ? (normalizedReferenceId ? [normalizedReferenceId] : [])
      : computeNextSelectionIds(selectedReferenceIdsRef.current, normalizedReferenceId, { multiSelect });
    if (next.length && !isDesktop) {
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
    isDesktop,
    isAssemblyView,
    referencePartId,
    revealStepTreeNode,
    stepModuleTreeSelectionDisabled,
    stepUpdateInProgress
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

  // Copy is clipboard-only. Adding context is an explicit host action.
  const deliverReferenceText = useCallback((text) => copyTextToClipboard(text), []);
  const referencesForHost = useCallback((text) =>
    referencesFromCopyText(text, cadFileParamForEntry(selectedEntry)).map((reference) => {
      const label = referenceLabel(reference.selector, displayStepTreeRoot || stepTreeRoot);
      return { ...reference, ...(label ? { label } : {}) };
    }), [selectedEntry, displayStepTreeRoot, stepTreeRoot]);
  const addReferenceText = useCallback((text) => {
    if (stepUpdateInProgress) return;
    for (const reference of referencesForHost(text)) onReference?.(reference);
  }, [onReference, referencesForHost, stepUpdateInProgress]);
  const hostReference = useMemo(
    () => (typeof onReference === "function" ? { deliverReference: deliverReferenceText, addReference: addReferenceText } : null),
    [onReference, deliverReferenceText, addReferenceText]
  );
  const handleAddSelection = useCallback(() => {
    addReferenceText(canonicalCopySelectionLines.join("\n"));
  }, [addReferenceText, canonicalCopySelectionLines]);

  const handleCopySelection = useCallback(async () => {
    setScreenshotStatus("");
    if (stepUpdateInProgress) {
      setCopyStatus("STEP update in progress. Please wait.");
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
    setScreenshotStatus,
    stepTreeCopyReferenceMap,
    stepTreeRoot,
    stepUpdateInProgress
  ]);

  const toggleStepTreeNode = useCallback((nodeId) => {
    const normalizedNodeId = String(nodeId || "").trim();
    if (!normalizedNodeId) {
      return;
    }
    const collapsing = expandedStepTreeNodeIds.includes(normalizedNodeId);
    const collapseExitsIsolation = collapsing &&
      isAssemblyView &&
      assemblyRoot &&
      focusedAssemblyNodeIds.some((focusedNodeId) => (
        assemblyNodeContainsNode(assemblyRoot, normalizedNodeId, focusedNodeId)
      ));
    const collapsedSubtreeIds = collapseExitsIsolation
      ? new Set(collectStepTreeSubtreeIds(displayStepTreeRoot || stepTreeRoot, normalizedNodeId))
      : null;
    setExpandedStepTreeNodeIds((current) => {
      if (current.includes(normalizedNodeId)) {
        return current.filter((id) => (
          collapsedSubtreeIds
            ? !collapsedSubtreeIds.has(id)
            : id !== normalizedNodeId
        ));
      }
      return uniqueStringList([...current, normalizedNodeId]);
    });
    if (collapseExitsIsolation) {
      setIsolatedAssemblyNodeIds((current) => {
        const next = current.filter((focusedNodeId) => (
          !assemblyNodeContainsNode(assemblyRoot, normalizedNodeId, focusedNodeId)
        ));
        return next.length === current.length ? current : next;
      });
    }
  }, [
    assemblyRoot,
    displayStepTreeRoot,
    expandedStepTreeNodeIds,
    focusedAssemblyNodeIds,
    isAssemblyView,
    stepTreeRoot
  ]);

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
    if (stepUpdateInProgress || stepModuleTreeSelectionDisabled) {
      return selectedPartIdsRef.current;
    }
    if (source !== "viewer") {
      setActiveTreeNodeScrollKey("");
    }
    const normalizedPartId = String(partId || "").trim();
    if (isAssemblyView && focusedAssemblyNodeIds.includes(normalizedPartId)) {
      return removeSelectedAssemblyNode(normalizedPartId);
    }
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
    if (next.length && !isDesktop) {
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
    isDesktop,
    isAssemblyView,
    focusedAssemblyNodeIds,
    removeSelectedAssemblyNode,
    revealStepTreeNode,
    renderPartIdForAssemblySelection,
    validAssemblySelectionIdSet,
    viewerSelectableAssemblyNodeIdSet,
    stepModuleTreeSelectionDisabled,
    stepUpdateInProgress
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
    if (!selector || appliedSelectReferenceKeyRef.current === selectReference.key || viewerLoading) {
      return;
    }
    const resolved = resolveSelectorSelection(selector, {
      referenceMap: effectiveActiveReferenceMap,
      treeRoot: displayStepTreeRoot || stepTreeRoot
    });
    if (!resolved) {
      return;
    }
    appliedSelectReferenceKeyRef.current = selectReference.key;
    if (resolved.kind === "reference") {
      if (selectedReferenceIdsRef.current.includes(resolved.id)) {
        revealStepTreeNode(findStepTreeTopologyNodeIdForReference(displayStepTreeRoot, resolved.id) || resolved.id, { source: "tree" });
      } else {
        toggleReferenceSelection(resolved.id, { source: "tree" });
      }
    } else if (selectedPartIdsRef.current.includes(resolved.id)) {
      revealStepTreeNode(resolved.id, { source: "tree" });
    } else {
      togglePartSelection(resolved.id, { source: "tree" });
    }
  }, [
    selectReference,
    viewerLoading,
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

  const focusStepTreeNode = useCallback((nodeId) => {
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
    for (const targetNodeId of targetNodeIds) {
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
    if (stepModuleTreeSelectionDisabled) {
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
    stepModuleTreeSelectionDisabled
  ]);

  const handleModelReferenceActivate = useCallback((referenceId, { multiSelect = false } = {}) => {
    if (stepUpdateInProgress || stepModuleTreeSelectionDisabled) {
      return;
    }
    const nextReferenceId = String(referenceId || "").trim();
    if (!nextReferenceId) {
      clearAssemblySelection();
      return;
    }
    const topologyReference = effectiveActiveReferenceMap.get(nextReferenceId) || null;
    if (topologyReference && isViewerTopologyReference(topologyReference)) {
      toggleReferenceSelection(nextReferenceId, { multiSelect });
      return;
    }
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
    if (!effectiveActiveReferenceMap.has(nextReferenceId)) {
      return;
    }
    toggleReferenceSelection(nextReferenceId, { multiSelect });
  }, [
    clearAssemblySelection,
    effectiveActiveReferenceMap,
    isViewerTopologyReference,
    resolvePickedAssemblyPartId,
    stepUpdateInProgress,
    toggleReferenceSelection,
    togglePartSelection,
    viewerInAssemblyMode,
    stepModuleTreeSelectionDisabled
  ]);

  const handleModelReferenceDoubleActivate = useCallback((referenceId) => {
    if (stepUpdateInProgress || stepModuleTreeSelectionDisabled || !isAssemblyView) {
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
    stepModuleTreeSelectionDisabled,
    stepUpdateInProgress
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
    if (stepUpdateInProgress || stepModuleTreeSelectionDisabled) {
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
      selectDisabled: focused || (!selected && hidden),
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
    stepModuleTreeSelectionDisabled,
    stepUpdateInProgress,
    viewerInAssemblyMode
  ]);

  const copyViewerContextMenuReference = useCallback(async (menu) => {
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
  }, [deliverReferenceText]);

  const copyStepTreeContextMenuReference = useCallback(async (id, { topology = false, toPrompt = false } = {}) => {
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
    selectedEntry,
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
    if (focusedAssemblyNodeIds.includes(nodeId)) {
      removeSelectedAssemblyNode(nodeId);
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
    setTabToolMode(normalizedMode);
    if (normalizedMode === TAB_TOOL_MODE.DRAW && drawingTool === DRAWING_TOOL.SURFACE_LINE) {
      setDrawingTool(DRAWING_TOOL.FREEHAND);
    }
  }, [drawingTool]);

  const handleEnableSelectableTopology = useCallback(() => {
    if (!selectedEntry || !selectedEntryHasReferences) {
      return;
    }
    setLargeFileState((current) => {
      const next = normalizeLargeFileState(current);
      return next.selectableTopologyEnabled
        ? next
        : { ...next, selectableTopologyEnabled: true };
    });
    setViewerAlertOpen(false);
    setTabToolMode(TAB_TOOL_MODE.REFERENCES);
  }, [selectedEntry, selectedEntryHasReferences]);

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
  }, [scheduleActiveFileSessionSave, onLodCameraMoved]);

  useCadWorkspaceShortcuts({
    copyStatus,
    screenshotStatus,
    setCopyStatus,
    setScreenshotStatus,
    previewMode,
    viewerAlertOpen,
    themeSheetOpen: false,
    tabToolsOpen,
    isDesktop,
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
    setThemeEditing,
    setTabToolsOpen,
    setFilesPanelOpen,
    setTabToolMode
  });

  // The viewport as a PNG, to the host (`onCapture`): the desktop app
  // attaches it to the composer. The toolbar shows the button only when the
  // host is listening.
  const handleCapture = useCallback(async () => {
    if (!selectedEntry || typeof onCapture !== "function") {
      return;
    }
    try {
      if (!viewerRef.current?.captureScreenshotBlob) {
        throw new Error("CAD Viewer not ready");
      }
      // Freeze selection before waiting for the image; deliver both as one bundle.
      const references = referencesForHost(canonicalCopySelectionLines.join("\n"));
      const blob = await viewerRef.current.captureScreenshotBlob();
      onCapture({ blob, file: cadFileParamForEntry(selectedEntry), references });
      setCopyStatus("");
      setScreenshotStatus("View captured");
    } catch (captureError) {
      setCopyStatus("");
      setScreenshotStatus(captureError instanceof Error ? captureError.message : "Capture failed");
    }
  }, [onCapture, selectedEntry, referencesForHost, canonicalCopySelectionLines]);

  // A host asking for the same picture from outside the viewport — the
  // desktop's composer has a `Ask about this view` item beside its attach
  // ones. `key` is a nonce, so two requests are two captures; the picture
  // goes to `onCapture` either way, and there is one capture path.
  const captureKey = captureRequest?.key ?? null;
  useEffect(() => {
    if (captureKey === null) {
      return;
    }
    void handleCapture();
    // Deliberately keyed on the nonce alone: re-running when `handleCapture`
    // is rebuilt (a new selection, a new host callback) would take a second
    // picture nobody asked for.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [captureKey]);

  const handleScreenshotCopy = useCallback(async () => {
    if (!selectedEntry) {
      return;
    }

    try {
      if (!viewerRef.current?.captureScreenshot) {
        throw new Error("CAD Viewer not ready");
      }
      await viewerRef.current.captureScreenshot();
      setCopyStatus("");
      setScreenshotStatus("Copied screenshot to clipboard");
    } catch (captureError) {
      setCopyStatus("");
      setScreenshotStatus(captureError instanceof Error ? captureError.message : "Clipboard copy failed");
    }
  }, [selectedEntry]);

  const handleEnterPreviewMode = useCallback(() => {
    const viewportContent = selectedViewportContent;
    if (viewerLoading || !viewportContent || previewMode) {
      return;
    }
    previewUiStateRef.current = {
      filesPanelOpen,
      tabToolsOpen,
      tabToolMode,
      themeEditing,
      viewerAlertOpen
    };
    setCopyStatus("");
    setScreenshotStatus("");
    setDrawingStrokes([]);
    setDrawingUndoStack([]);
    setDrawingRedoStack([]);
    setViewerAlertOpen(false);
    setThemeEditing(false);
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
    themeEditing,
    viewerAlertOpen,
    viewerLoading
  ]);

  // Exit orbit/preview mode and restore the pre-preview UI, from the floating
  // toolbar's "Exit orbit" button. Mirrors the Escape-key exit in
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
      setThemeEditing(previousUiState.themeEditing);
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
  const selectionCount = selectionCountBase;
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
  const fileSheetOpen = !!selectedFileSheetKind && selectedFileSheetHasSections && tabToolsOpen && !previewMode && !themeEditing;
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
  const renderDisplaySettings = displaySettings;
  const themeTabs = [
    // One tab for everything about how this file is drawn right now: display
    // mode, plus the section-plane and exploded-view transforms. All three are
    // per-file session state. The theme is global, not file-specific —
    // it lives in the navbar-triggered theme editor (ThemeEditorPanel).
    supportsDisplayModes
      ? buildDisplaySettingsTab({
          displaySettings,
          updateDisplaySettings,
          clipBounds: selectedMeshData?.bounds || null,
          explodeMeshData: selectedMeshData || null
        })
      : null
  ].filter(Boolean);

  return (
    <FileSheetTabPreferencesContext.Provider value={{ store: preferences.fileSheetTabs || {}, update: (fileSheetTabs) => onPreferenceChange({ fileSheetTabs }) }}>
    <TutorialTipsContext.Provider value={tips}>
    <HostPanelSlotContext.Provider value={hostPanelSlot}>
    <FileSheetPortalContext.Provider value={hostElement}>
    <HostReferenceContext.Provider value={hostReference}>
    <div
      className={cn("relative flex h-full min-h-0 flex-col overflow-hidden bg-background text-foreground", className)}
      data-slot="cad-file-view"
      data-cad-surface
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
                  viewerRef={viewerRef}
                  renderFormat={effectiveRenderFormat}
                  drawingThicknessScale={drawingThicknessScale}
                  planMode={selectedEntryIsDrawing && drawingViewMode === "2d"}
                  bendAxisX={selectedEntryIsDrawing ? selectedEntry?.bendAxisX || null : null}
                  drawingBendLines={selectedEntryIsDrawing ? drawingBendLines : null}
                  bendAnglesRad={selectedEntryIsDrawing ? drawingBendAnglesRad : null}
                  drawingBends={selectedEntryIsDrawing ? drawingBends : null}
                  drawingBendStyle={selectedEntryIsDrawing ? drawingBendStyle : "boxed"}
                  drawingBendRadiusMm={selectedEntryIsDrawing ? drawingBendRadiusMm : 0}
                  drawingKFactor={selectedEntryIsDrawing ? drawingKFactor : DXF_DEFAULT_KFACTOR}
                  drawingHiddenLayers={selectedEntryIsDrawing ? drawingHiddenLayers : null}
                  drawingOrientation={selectedEntryIsDrawing ? drawingOrientation : null}
                  drawingMaterialColor={selectedEntryIsDrawing ? dxfMaterialPreset(drawingMaterial).colorHex : null}
                  drawingGeometry={selectedEntryIsDrawing ? drawingGeometry : null}
                  drawingIsDocument={selectedEntryIsDrawingDocument}
                  drawingThicknessMm={selectedEntryIsDrawing ? drawingThicknessMm : 0}
                  onCameraZoomPercentChange={setViewerZoomPercent}
                  renderPartsIndividually={
                    isUrdfView || Boolean(selectedStepParameterRuntime) || Boolean(selectedAnimationRuntime)
                  }
                  stepParameters={selectedStepParameterRuntime}
                  stepAnimation={selectedAnimationRuntime}
                  selectedMeshData={selectedMeshData}
                  selectedKey={selectedKey}
                  missingFileRef={missingFileRef}
                  viewerServerInfo={viewerServerInfo}
                  viewerPerspective={viewerPerspective}
                  viewerPerspectiveRef={activePerspectiveRef}
                  themeSettings={resolvedThemeSettings}
                  displaySettings={renderDisplaySettings}
                  previewMode={previewMode}
                  viewerLoading={viewerLoading}
                  viewerAlert={viewerAlert}
                  stepUpdateInProgress={effectiveRenderFormat === RENDER_FORMAT.STEP && stepUpdateInProgress}
                  referenceSelectionPending={referenceSelectionPending}
                  referenceSelectionUnavailable={referenceSelectionUnavailable}
                  referenceSelectionDeferred={selectedTopologyDeferredByCost}
                  viewerMode={viewerMode}
                  assemblyPickingActive={viewerInAssemblyMode}
                  assemblyParts={viewerAssemblyRenderParts}
                  hiddenPartIds={viewerHiddenPartIds}
                  selectedPartIds={viewerSelectedPartIds}
                  hoveredPartId={viewerHoveredPartIds}
                  hoveredReferenceId={effectiveHoveredReferenceId}
                  selectedReferenceIds={selectedReferenceIds}
                  selectorRuntime={effectiveSelectorRuntime}
                  displayEdgeRuntime={selectedDisplayEdgeRuntime}
                  pickableFaces={viewerPickableFaces}
                  pickableEdges={viewerPickableEdges}
                  pickableVertices={viewerPickableVertices}
                  focusedPartIds={viewerFocusedPartIds}
                  boundsAnimationActive={robotBoundsAnimationActive}
                  drawToolActive={drawToolActive}
                  measureModeActive={measureModeActive}
                  drawingTool={drawingTool}
                  drawingStrokes={drawingStrokes}
                  handleDrawingStrokesChange={handleDrawingStrokesChange}
                  handlePerspectiveChange={handlePerspectiveChange}
                  handleModelHoverChange={handleModelHoverChange}
                  handleModelReferenceActivate={handleModelReferenceActivate}
                  handleModelReferenceDoubleActivate={handleModelReferenceDoubleActivate}
                  handleModelReferenceContext={handleModelReferenceContext}
                  onMeasurePick={handleMeasurePick}
                  onMeasureHoverPoint={handleMeasureHoverPoint}
                  activeMeasurementId={activeMeasureId}
                  measureState={measureRulerState}
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
                  copyReferenceTipActive={copyReferenceTipActive}
                  panToolActive={panToolActive}
                  handleCopySelection={handleCopySelection}
                  handleAddSelection={typeof onReference === "function" ? handleAddSelection : null}
                  handleScreenshotCopy={handleScreenshotCopy}
                />
              </div>

              <FloatingToolBar
                previewMode={previewMode}
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
                handleCapture={typeof onCapture === "function" ? handleCapture : null}
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
                viewerLoading={effectiveViewerLoading}
                previewMode={previewMode}
                progress={selectedLoadProgress}
              />
            </div>

            {selectedFileSheetKind === "step" ? (
              <StepFileSheet
                key={`step:${selectedKey}`}
                open={fileSheetOpen}
                isDesktop={isDesktop}
                width={activeSheetWidth || tabToolsWidth}
                onOpenChange={setTabToolsOpen}
                onStartResize={fileSheetResizeHandler}
                selectedEntry={selectedEntry}
                viewerLoading={viewerLoading || assemblySidebarLoading}
                isAssemblyView={isAssemblyView}
                measurements={measureMeasurements}
                activeMeasurementId={activeMeasureId}
                measureModeActive={measureModeActive}
                onMeasurementActivate={setActiveMeasureId}
                onMeasurementDelete={handleMeasureDelete}
                onMeasurementsClear={handleMeasureClear}
                stepTreeRoot={displayStepTreeRoot}
                expandedTreeNodeIds={expandedStepTreeNodeIds}
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
                onCopyTreeNodeReference={copyStepTreeContextMenuReference}
                onFocusTreeNode={focusStepTreeNode}
                onUnfocusTreeNode={handleExitSingleIsolate}
                onExitAllIsolate={handleExitIsolate}
                onHideOtherTreeNode={handleHideOtherTreeNode}
                onToggleTreeNode={toggleStepTreeNode}
                onClearSelection={clearAssemblySelection}
                onHoverTreeNode={setHoveredListPartId}
                onHoverReferenceNode={setHoveredListReferenceId}
                treeSelectionDisabled={stepModuleTreeSelectionDisabled}
                treeSelectionDisabledReason={stepModuleTreeSelectionDisabledReason}
                onTogglePartVisibility={togglePartVisibility}
                hideOtherSelectedParts={handleHideOtherSelectedParts}
                hideAllParts={handleHideAllParts}
                showAllHiddenParts={handleShowAllHiddenParts}
                exitIsolate={handleExitIsolate}
                stepModule={{
                  status: selectedStepModuleStatus,
                  error: selectedStepModuleError,
                  definition: selectedStepModuleDefinition,
                  enabled: stepModuleEnabled,
                  parameterValues: stepModuleParameterValues,
                  onParameterChange: handleStepModuleParameterChange,
                  onResetParameters: handleResetParameters,
                  onApplyPose: handleApplyPose,
                  onEnabledChange: handleStepModuleEnabledChange,
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
                themeTabs={themeTabs}
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
                isDesktop={isDesktop}
                width={activeSheetWidth || tabToolsWidth}
                selectedEntry={selectedEntry}
                onOpenChange={setTabToolsOpen}
                onStartResize={fileSheetResizeHandler}
                joints={movableUrdfJoints}
                groupStates={selectedUrdfGroupStates}
                activeGroupStateId={activeSelectedUrdfGroupStateId}
                jointValues={selectedUrdfJointValues}
                onJointValueChange={handleUrdfJointValueChange}
                onGroupStateSelect={handleSelectUrdfGroupState}
                onCopyJointAngles={handleCopyUrdfJointAngles}
                onResetPose={handleResetUrdfPose}
                sdf={selectedFileSheetKind === "sdf" ? {
                  info: selectedUrdfData?.sdf || null
                } : null}
                viewerServerInfo={viewerServerInfo}
                suppressDynamicMetadataStatus={selectedArtifactGenerating}
                statusItems={selectedFileStatusItems}
                themeTabs={themeTabs}
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
                isDesktop={isDesktop}
                width={activeSheetWidth || tabToolsWidth}
                selectedEntry={selectedEntry}
                onOpenChange={setTabToolsOpen}
                onStartResize={fileSheetResizeHandler}
                viewerServerInfo={viewerServerInfo}
                suppressDynamicMetadataStatus={selectedArtifactGenerating}
                statusItems={selectedFileStatusItems}
                themeTabs={[
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
                  ...themeTabs
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
                isDesktop={isDesktop}
                width={activeSheetWidth || tabToolsWidth}
                selectedEntry={selectedEntry}
                onOpenChange={setTabToolsOpen}
                onStartResize={fileSheetResizeHandler}
                viewerServerInfo={viewerServerInfo}
                suppressDynamicMetadataStatus={selectedArtifactGenerating}
                statusItems={selectedFileStatusItems}
                themeTabs={themeTabs}
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

            {themeEditing ? (
              <ThemeEditorPanel
                open
                isDesktop={isDesktop}
                width={activeSheetWidth || tabToolsWidth}
                onClose={closeThemeEditor}
                onStartResize={fileSheetResizeHandler}
                themeSettings={themeSettings}
                themeId={themeId}
                resolvedColorSchemeMode={resolvedColorSchemeMode}
                onSelectTheme={selectTheme}
                updateThemeSettings={updateThemeSettings}
              />
            ) : null}

            {/*
              The host's panel column, at the right end of the body row and
              nowhere else. The host draws the frame — one border, one width,
              one resize handle (`@hardcore/ui/navigation`'s `FilePanelColumn`) — and
              hands the box back as `panelSlot`, so the surface's own theme
              editor and Inspector are portaled into the same column its file
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
          viewerAlertOpen={viewerAlertOpen}
          viewerAlert={viewerAlert}
          previewMode={previewMode}
          setViewerAlertOpen={setViewerAlertOpen}
        />
      </div>
    </div>
    </HostReferenceContext.Provider>
    </FileSheetPortalContext.Provider>
    </HostPanelSlotContext.Provider>
    </TutorialTipsContext.Provider>
    </FileSheetTabPreferencesContext.Provider>
  );
}

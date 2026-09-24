import { buildEdgeChainGraph } from "./workbench/edgeChainSelection.js";
"use client";

import SelectionFilterMenu, { ToolFilterNote } from "./components/workbench/SelectionFilterMenu.jsx";
import { MEASURE_SELECTION_FILTERS, SELECTION_FILTERS } from "./workbench/selectionFilter.js";
import { CirclePlay, MousePointer2, Ruler, SplinePointer, SquareSplitHorizontal, UnfoldVertical } from "lucide-react";
import { stepGeometryContextText, stepGeometryPromptText } from "./workbench/stepGeometryPrompt.js";
import { filterSelectionReferences, toggleReferenceGroupSelection, connectedReferenceIds } from "./workbench/selectionFilter.js";
import { buildTangentFaceGraph } from "./workbench/tangentFaceSelection.js";

import * as THREE from "three";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { hasAuthoredMaterials } from "@hardcore/core/common/inspectEnvironment.js";
import { displayRecordsBounds, mergeBoundsList } from "@hardcore/core/lib/viewer/autoZoom.js";
import { VIEWER_PICK_MODE } from "@hardcore/core/lib/viewer/constants.js";
import { runtimeModelKeyMatches, toNumber } from "@hardcore/core/lib/viewer/modelRuntime.js";
import { normalizePartIdList } from "@hardcore/core/lib/viewer/partVisualState.js";
import { PromptContextAction } from "../../host/PromptContextAction.js";
import RendererShell from "../kit/shell/RendererShell.jsx";
import { useRendererShell } from "../kit/shell/useRendererShell.js";
import { readShellState, shellPresentationKey } from "../kit/shell/shellState.js";
import StepSceneLayers, { releaseStepRuntime } from "./scene/StepSceneLayers.jsx";
import { createStepScene, stepSceneView } from "./scene/stepScene.js";
import { useStepViewPolicy, viewDrawsHairlines } from "./scene/useStepViewPolicy.js";
import {
  viewerHiddenPartIdsForRenderPane, viewerPickModeForRenderPane, viewerSelectedPartIdsForRenderPane,
  viewerSelectorRuntimeForRenderPane
} from "./workbench/viewerPickMode.js";
import { viewportMenuEntries } from "./components/workbench/AssemblyContextMenuItems.js";
import { useViewportLod } from "./render/useViewportLod.js";
import { lodSceneMayMove, sampleLodCamera } from "./render/lodCameraSample.js";
import { registerLodDisplaySource } from "./render/lodSceneAdoption.js";
import { ALL_VIEW_FEATURES, EDGELESS_VIEW_FEATURES } from "@hardcore/core/common/viewSettings.js";
import { explodablePartCount } from "./workbench/explodableParts.js";
import { useStepPanel } from "./components/workbench/StepPanel.js";
import { CAD_PANEL } from "../../file-viewer/navigation/panels.js";
import { restoreMotionAnimation, restoreMotionParameters } from "./workbench/motionRestore.js";
import { useStepMotionControls } from "./workbench/useStepMotionControls.js";
import { animationControlsHaveContent } from "./components/workbench/AnimationControlsSection.js";
import { useCadAssets } from "./components/workbench/hooks/useCadAssets.js";
import { useEditingPreview } from "./components/workbench/hooks/useEditingPreview.js";
import { useViewportQualityStatus } from "./components/workbench/hooks/useViewportQualityStatus.js";
import { previewGeometryChanged } from "./workbench/editingPreview.js";
import MeasurePanel from "./components/workbench/MeasurePanel.jsx";
import ViewToolPanel from "./components/workbench/ViewToolPanel.jsx";
import { CrossSectionControls, ExplodeControls } from "../kit/view-settings/DisplaySettingsSection.js";
import { useCadWorkspaceSelection } from "./components/workbench/hooks/useCadWorkspaceSelection.js";
import { useCadWorkspaceSelectors } from "./components/workbench/hooks/useCadWorkspaceSelectors.js";
import { useAppliedViewSettings } from "../kit/view-settings/useAppliedViewSettings.js";
import { useViewSettings } from "../kit/view-settings/useViewSettings.js";
import {
  ASSET_STATUS,
  CAD_TOOL_MODES,
  CAD_TOOL_RESTORE,
  REFERENCE_STATUS,
  TAB_TOOL_MODE
} from "./workbench/constants.js";
import { promptDeliveryMessage } from "../kit/shell/promptContext.js";
import { readStepRecord, stepRecordSignatures, writeStepRecord } from "./workbench/stepSessionRecord.js";
import {
  entrySourceFormat,
  fileSheetKindForEntry
} from "@hardcore/core/lib/fileFormats.js";
import {
  assetKindForRenderFormat,
  hasCapability,
  isArtifactManagedFormat,
  parameterSourceKind,
  supportsTool,
  ASSET_KIND,
  PARAMETER_SOURCE
} from "@hardcore/core/lib/renderCapabilities.js";
import {
  buildViewerMeshAlert,
  buildViewerEditAlert
} from "./workbench/viewerAlerts.js";
import {
  buildParameterValuesCopyText,
  parseParameterValuesPasteText
} from "./workbench/parameterControls.js";
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
  topologyCompositionKeyMatches,
  uniqueStringList
} from "./workbench/referenceSelection.js";
import {
  entryAssetHash,
  entryHasDisplayEdges,
  entryHasMesh,
  entryHasReferences,
  entryMeshAssetSignature,
  entryPoseUrl
} from "@hardcore/core/lib/entryAssets.js";
import {
  hasMeshGeometry,
  hasStepGlbByteCost,
  isLargeMeshData,
  isLargeStepGlbEntry
} from "@hardcore/core/lib/render/meshCost.js";
import {
  animationClipList,
  animationRenderFrame,
  buildDefaultAnimationState,
  findAnimationClip,
} from "@hardcore/core/common/animationClock.js";
import { createAnimationClock, AnimationClockProvider, useAnimationClockStore } from "./workbench/animationClockStore.js";
import { resolveStepModuleLoad } from "./workbench/stepModuleLoad.js";
import {
  applyMeasureRulerDelete,
  applyMeasureRulerHover,
  applyMeasureRulerPick,
  cancelMeasureRulerDraft,
  clearMeasureRulerMeasurements,
  measureRulerStateForChange
} from "./workbench/measureRulerState.js";
import { cadFileParamForEntry, cadPathForEntry, fileKey } from "./workbench/entryPaths.js";
import {
  stepModuleRequiresTopology,
  stepModuleTopologyOccurrenceIds
} from "./workbench/topologyCapabilities.js";
import { shortestUniquePathSuffixes } from "@hardcore/core/lib/filePathSuffix.js";
import { stepJointHandles, stepPosableDofs } from "./workbench/jointHandles.js";
import {
  buildFileStatusItems,
} from "./workbench/fileStatusItems.js";
import { useArtifact } from "./components/workbench/hooks/useArtifact.js";
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
} from "./workbench/assemblyIsolation.js";
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
} from "./components/workbench/hooks/packageProgressiveLoad.js";
import { meshLoadErrorForViewer, shouldStartMeshLoad } from "./components/workbench/hooks/meshLoadTarget.js";
import {
  kinematicsModuleDefinitionFromSidecar,
  loadKinematicsModuleDefinition,
  previewKinematicsModuleDefinition
} from "@hardcore/core/common/kinematicsModule.js";
import { validateSourceSidecar } from "@hardcore/core/common/sourceSidecar.js";
import { loadSourceAnimation, validateAnimationClips } from "@hardcore/core/common/renderModule.js";
import { useViewerHost, usePromptDestination } from "../../host/context.js";
import { createCadPromptContext } from "./file-view/promptContext.js";
import { HostReferenceContext, referenceLabel, referencesFromCopyText, resolveSelectorSelection } from "./file-view/hostReference.js";
import { applySourceAppearanceToMeshData, sourceAppearanceGeometry } from "@hardcore/core/common/sourceSidecar.js";
const TOPOLOGY_FILTER_NOUNS = Object.freeze({
  faces: "faces", edges: "edges", "tangent-faces": "faces", "edge-chain": "edges"
});
const EMPTY_MATERIAL_OVERRIDES = Object.freeze({});
// --- zoom to selection -------------------------------------------------------
// What a selection occupies NOW: the boxes of its references, from the selector runtime as
// posed, merged with the boxes of its parts, from the records on screen (explosion included).
function pointBounds(center) {
  if (!Array.isArray(center) && !ArrayBuffer.isView(center)) return null;
  const point = [toNumber(center[0]), toNumber(center[1]), toNumber(center[2])];
  return { min: point, max: [...point] };
}

function selectorReferenceForId(selectorRuntime, referenceId) {
  const id = String(referenceId || "").trim();
  if (!id || !selectorRuntime) return null;
  return selectorRuntime.referenceMap?.get?.(id) ||
    selectorRuntime.faceReferenceMap?.get?.(id) ||
    selectorRuntime.edgeReferenceMap?.get?.(id) ||
    selectorRuntime.referenceByDisplaySelector?.get?.(id) ||
    selectorRuntime.referenceByNormalizedSelector?.get?.(id) ||
    null;
}

function selectorReferenceBounds(selectorRuntime, referenceIds = []) {
  const boundsList = [];
  for (const referenceId of normalizePartIdList(referenceIds)) {
    const reference = selectorReferenceForId(selectorRuntime, referenceId);
    const bbox = reference?.pickData?.bbox || reference?.bbox || null;
    const bounds = mergeBoundsList([bbox]) || pointBounds(reference?.pickData?.center || reference?.center);
    if (bounds) boundsList.push(bounds);
  }
  return mergeBoundsList(boundsList);
}

function displayRecordBoundsForPartIds(runtime, partIds = []) {
  const normalizedPartIds = normalizePartIdList(partIds);
  if (!normalizedPartIds.length || !Array.isArray(runtime?.displayRecords)) return null;
  const translationByRecord = new Map();
  for (const record of runtime.displayRecords) {
    const elements = record?.explodedViewMatrix?.elements;
    if (!elements || elements.length < 16) continue;
    const translation = new THREE.Vector3(toNumber(elements[12]), toNumber(elements[13]), toNumber(elements[14]));
    if (translation.lengthSq() > 1e-12) translationByRecord.set(record, translation);
  }
  return displayRecordsBounds(runtime.displayRecords, { partIds: new Set(normalizedPartIds), translationByRecord });
}
function sourceAnimationForEntry(entry) { return (entry?.editingPreview ? entry.previewAnimation : entry?.sourceSidecar?.animation) || null; }
function sourceAnimationKeyForEntry(entry) { return sourceAnimationForEntry(entry) ? `${fileKey(entry)}:${entry?.animationHash || entry?.documentHash || entry?.hash || "animation"}` : ""; }

import {
  DEFAULT_LARGE_FILE_STATE,
  EMPTY_LIST,
  entryWithoutRenderAssets,
  normalizeLargeFileState
} from "./file-view/fileViewState.js";
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
} from "./file-view/stepTreeSelection.js";

// The shared renderer consumes one prepared entry. FileViewer owns navigation,
// panel placement and persistence; the connection owns catalog subscriptions.
export default function StepSurface(props) {
  const clock = useMemo(() => createAnimationClock(), []);
  return <AnimationClockProvider value={clock}><StepSurfaceBody {...props} /></AnimationClockProvider>;
}


function StepSurfaceBody({
  client, entry, serverInfo, renderSession: cadRenderSession, preferences, onPreferenceChange, onOpenFile, className = "",
  panelSlot, colorScheme = "light", selectReference, captureRequest, acknowledgeCommand, documentResource, slots, live,
  fullscreen = false, onFullscreenChange, onNavigationActionsChange,
  openPanel = "", onPanelOpen, onChromeVisibilityChange, onReload, state, onStateChange
}) {
  // The host's props, as the shell reads them. This renderer took them apart before the
  // shell existed; it hands the same things back under the names every renderer uses.
  const view = {
    fullscreen, openPanel, onPanelOpen, onChromeVisibilityChange,
    onNavigationActionsChange, onStateChange, state, panelSlot, onOpenFile,
    reload: onReload, onFullscreenChange, appearance: { colorScheme }
  };
  const services = { preferences, onPreferenceChange, live, captureRequest, acknowledgeCommand };
  const host = useViewerHost();
  const destination = usePromptDestination();
  const promptAvailable = destination.available;
  const composerDestination = destination.kind === "composer";
  const animationClock = useAnimationClockStore();
  const { getAnimationClock, resetAnimationClock, setAnimationClock } = animationClock;
  const [restoredState] = useState(() => readShellState(state).renderer);
  // What the stored slices were written against, for the effects that restore them.
  const recordSignaturesRef = useRef(null);
  const resolvedColorSchemeMode = colorScheme === "dark" ? "dark" : "light";
  const storeSnapshot = useSyncExternalStore(client.subscribe, client.getSnapshot, client.getSnapshot);
  const selectedKey = fileKey(entry);
  const liveEntry = storeSnapshot.entries.find((item) => fileKey(item) === selectedKey) || entry;
  const manifestRevision = storeSnapshot.revision;
  const explicitFileParam = cadFileParamForEntry(entry);
  const viewerServerInfo = serverInfo;
  const catalogHydrated = storeSnapshot.hydrated;
  const catalogError = storeSnapshot.error || "";
  const selectedCatalogPending = liveEntry?.catalogPending === true;
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
  // The viewport's handle, and the ONE coordinator that drives it. Both are this
  // renderer's: what it loads, and how much detail it asks for, is decided from the
  // RESOLVED view — long before it can describe its own load to the shell.
  const viewerRef = useRef(null);
  // ONE scene per mounted file, made HERE rather than in the viewport: the shell hook is
  // handed a scene, and it runs in this function, above the viewport it mounts.
  const [stepScene] = useState(() => createStepScene(THREE));
  const viewUpdate = useAppliedViewSettings(desiredScene, selectedKey, viewerRef, viewSettingsStore);
  const resolvedScene = viewUpdate.scene;
  const [hoveredListPartId, setHoveredListPartId] = useState("");
  const [hoveredModelPartId, setHoveredModelPartId] = useState("");
  const [stepUpdateInProgress, setStepUpdateInProgress] = useState(false);
  // The viewport's own alert, kept HERE: this renderer folds it into an alert of its own
  // (`viewerAlert` below) and hands the shell the composed result.
  const [viewerRuntimeAlert, setViewerRuntimeAlert] = useState(null);
  const rendering = resolvedScene.render.enabled;
  const resolvedThemeSettings = resolvedScene.theme;
  const resolvedMaterialOverrides = resolvedScene.materialOverrides || EMPTY_MATERIAL_OVERRIDES;
  const resolvedDisplayEdgeSettings = resolvedScene.display.edges;
  const previewMode = fullscreen;
  const [tabToolMode, setTabToolMode] = useState(() => CAD_TOOL_MODES.restore(readShellState(state).tool));
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

  const fileSessionNamespace = selectedKey;

  const {
    meshState,
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
    setReferenceError,
    displayEdgeState,
    setDisplayEdgeState,
    displayEdgeStatus,
    setDisplayEdgeStatus,
    displayEdgeError,
    setDisplayEdgeError,
    cancelMeshLoad,
    cancelReferenceLoad,
    cancelDisplayEdgeLoad,
    loadMeshForEntry,
    loadReferencesForEntry,
    loadDisplayEdgesForEntry,
    fatalLoadFailure
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
  // This renderer serves .step/.stp and nothing else (`index.ts` matches no other
  // extension), so "is the entry a STEP" is "is the entry the file that opened this
  // renderer". Asked once, here, rather than re-derived at every gate that used to be a
  // per-format branch in the shared stack.
  // This renderer is only ever handed a STEP: its `matches` (index.ts) excludes every other
  // format the viewer knows by extension. So "is this a STEP" is "is there a file", and asking
  // the format again here was the last identity check left in the surface.
  const isStepEntry = Boolean(selectedEntry);
  // Every entry renders from its own source format: nothing is baked into a package
  // under a different one.
  const selectedEntryRenderAssetFormat = selectedEntrySourceFormat;
  const selectedFileSheetKind = fileSheetKindForEntry(selectedEntry);
  // The URL's path IS the directory, so there is nothing to select and no state to
  // reconcile — the Viewer always has exactly one directory, the one it was opened at.
  const stepArtifactGenerationAvailable = viewerServerInfo
    ? viewerServerInfo.stepArtifactGenerationAvailable !== false
    : true;
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
    isStepEntry &&
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
      const restoredSessionState = readStepRecord(restoredState, recordSignaturesRef.current);
      // A sidecar with no kinematics section resolves to a NULL definition —
      // an animation-only model has a sidecar and lands here — so the ready
      // state is committed from one place that expects that (see
      // workbench/stepModuleLoad); the Position section is then absent, not empty.
      const resolved = resolveStepModuleLoad({
        url: selectedStepModuleUrl,
        definition,
        restored: restoredSessionState.pose
      });
      setStepModuleLoadState(resolved.loadState);
      const parameterValues = restoreMotionParameters(definition, resolved.parameterValues,
        motionRevisionRef.current === loadMotionRevision ? restoredSessionState.animation : animationStateRef.current);
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
        const restoredSessionState = readStepRecord(restoredState, recordSignaturesRef.current);
        const nextState = restoreMotionAnimation(
          motionRevisionRef.current === loadMotionRevision ? restoredSessionState.animation : animationStateRef.current, clips);
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
  const effectiveViewerLoading = viewerLoading || selectedArtifactGenerating || selectedCatalogPending;
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
  // The revision half of the shell's presentation token: what is being shown, and whether it
  // is all of it yet. The shell builds the token and hands it to the viewport; this renderer
  // builds the same one, because only it can answer whether a live edit's own result has landed.
  const presentationRevisionKey = `${selectedMeshData ? meshState?.meshHash || selectedMeshHash : selectedMeshHash}:${selectedMeshPartial ? "partial" : "complete"}`;
  const presentationKey = shellPresentationKey(selectedKey, presentationRevisionKey);
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

  const viewerAlert = useMemo(() => {
    const editFailure = buildViewerEditAlert(editingPreview.state, currentPreviewVisible, Boolean(selectedMeshData && !selectedMeshPartial));
    if (editFailure) return editFailure;
    if (catalogError && !selectedMeshData) return {
      severity: "error", kind: "status", title: "Couldn’t open the model",
      message: "The viewer couldn’t retrieve this file’s information.",
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
  // This is the displayed render revision, so same-file saves cannot inherit
  // a predecessor's scheduler or benchmark milestones.
  const viewportQualityModelKey = `${selectedEntry?.file || ""}:${selectedMeshHash || selectedEntry?.hash || ""}`;
  // Viewport LOD (design/unified-tessellation.md Phase 5): camera-settle
  // driven re-tessellation of the components that project the worst error.
  // The viewport's own seams, filled in when it mounts: the live WebGL runtime, the layers'
  // published selector runtime, and "what reference is under this point" for the menu.
  const runtimeRefRef = useRef(null);
  const layersApiRef = useRef(null);
  const pickAtRef = useRef(null);
  const lodSelectedPartIdsRef = useRef(EMPTY_LIST);
  const modelKeyRef = useRef(selectedKey);
  modelKeyRef.current = selectedKey;
  // Declared here, above the LOD scheduler that is handed it: it reads only refs, so it is
  // safe this early, and a `const` read before its declaration is a TDZ crash, not undefined.
  const sampleViewportLodCamera = useCallback((options) => {
    const runtime = runtimeRefRef.current?.current;
    if (!runtimeModelKeyMatches(runtime, modelKeyRef.current)) return null;
    return sampleLodCamera(THREE, runtime, { ...options, selectedPartIds: lodSelectedPartIdsRef.current });
  }, []);
  const { onCameraMoved: onLodCameraMoved } = useViewportLod({
    resources: client.resources,
    sampleCamera: sampleViewportLodCamera,
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
  // Publishes the readiness moments (first geometry, standard detail) that harnesses read.
  useViewportQualityStatus({
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
  const selectedFileSheetKeyRef = useRef("");
  const handleViewerAlertChange = useCallback((nextAlert) => {
    setViewerRuntimeAlert(nextAlert || null);
  }, []);


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

  // A routine that failed to load has no Animate tool to say so on: it is one of the file's
  // Issues instead.
  const annotationAlert = useMemo(() => (selectedAnimationError ? {
    severity: "warning", blocking: false,
    summary: "Animation unavailable",
    title: "Animation unavailable",
    message: "The geometry is visible, but its animation could not be loaded, so the Animate tool is not offered.",
    details: `File: ${fileKey(selectedEntry)}\n${selectedAnimationError}`,
  } : null), [selectedAnimationError, selectedEntry]);
  const selectedFileStatusItems = useMemo(() => (
    selectedArtifactGenerating
      ? []
      : buildFileStatusItems({
        entry: selectedEntry,
        fileSheetKind: selectedFileSheetKind,
        stepSourceStatus: selectedStepSourceStatus,
        viewerAlert,
        warningAlert: annotationAlert,
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
    annotationAlert,
    viewerServerInfo
  ]);


  // ---- this STEP's own slice of the per-file record --------------------------------------
  // Read when the record is WRITTEN, never at render: the pose is written outside React, and
  // while a clip plays the authoritative time is the clock store's, not React state's.
  const recordSignatures = useMemo(() => stepRecordSignatures(selectedEntry), [selectedEntry]);
  recordSignaturesRef.current = recordSignatures;
  const recordInputsRef = useRef(null);
  recordInputsRef.current = {
    tree: { referenceQuery, selectedReferenceIds, selectedPartIds, expandedStepTreeNodeIds, hiddenPartIds },
    pose: { parameterValues: stepModuleParameterValues },
    animation: {
      activeClipId: animationState.activeClipId, enabled: animationState.enabled,
      elapsedSec: animationState.playing ? getAnimationClock() : animationState.elapsedSec,
      speed: animationState.speed, loopEnabled: animationState.loopEnabled
    },
    largeFile: { selectableTopologyEnabled: largeFileState.selectableTopologyEnabled },
    signatures: recordSignatures
  };
  const rendererState = useCallback(() => writeStepRecord(recordInputsRef.current), []);
  // The record is written soon after anything in it changes. A clip that is PLAYING writes
  // nothing: the clock moves every frame, and the stored time would be rewritten with it.
  const scheduleRecordSave = useCallback(() => { if (!animationStateRef.current.playing) shellRef.current?.scheduleStateSave(); }, []);
  useEffect(() => { scheduleRecordSave(); }, [scheduleRecordSave, referenceQuery, selectedReferenceIds, selectedPartIds,
    expandedStepTreeNodeIds, hiddenPartIds, stepModuleParameterValues, animationState, largeFileState, recordSignatures]);

  // Everything this file was left with, once, before the first paint.
  const sessionRestoredRef = useRef(false);
  useLayoutEffect(() => {
    if (sessionRestoredRef.current) return;
    sessionRestoredRef.current = true;
    const restored = readStepRecord(restoredState, recordSignatures);
    setReferenceQuery(restored.tree.referenceQuery);
    selectedReferenceIdsRef.current = restored.tree.selectedReferenceIds;
    setSelectedReferenceIds(restored.tree.selectedReferenceIds);
    selectedPartIdsRef.current = restored.tree.selectedPartIds;
    setSelectedPartIds(restored.tree.selectedPartIds);
    setExpandedStepTreeNodeIds(restored.tree.expandedStepTreeNodeIds);
    setHiddenPartIds(restored.tree.hiddenPartIds);
    setLargeFileState(normalizeLargeFileState(restored.largeFile));
    if (restored.pose) {
      // Definition normalization happens when the sidecar arrives. A routine that owns the
      // pose wins outright: the losing owner's raw values are cleared immediately.
      const values = restored.animation?.enabled !== false && restored.animation?.activeClipId ? {} : restored.pose.parameterValues;
      stepModuleParameterValuesRef.current = values;
      setStepModuleParameterValues(values);
    }
    // The animation slice restores against the CLIPS this model actually compiled, which is
    // why it is resolved through restoreMotionAnimation rather than trusted as stored.
    if (restored.animation) {
      const state = restoreMotionAnimation(restored.animation,
        animationLoadState.url === sourceAnimationKeyForEntry(selectedEntry) ? animationLoadState.clips : null);
      animationStateRef.current = state;
      setAnimationState(state);
      setAnimationClock(state.elapsedSec);
    }
  }, []);

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
      fatalFailure: fatalLoadFailure,
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
    fatalLoadFailure,
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
    isStepEntry &&
    selectedEntryHasReferences &&
    !isAssemblyView;
  const topologyCapabilityRequested = selectedStepPartRootActive;
  const plainStepReferencePickingRequested =
    plainStepReferencePickingEnabled &&
    (topologyCapabilityRequested || selectedStepModuleTopologyRequested);
  const assemblyStepTreeTopologyLoadingEnabled =
    isStepEntry &&
    selectedEntryHasReferences &&
    isAssemblyView &&
    requestedStepTreeTopologyNodeIds.length > 0;
  const selectedStepDisplayEdgesRequested =
    isStepEntry &&
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
    inspectedAssemblyPartTopologyReferences: EMPTY_LIST,
    selectedReferenceIds,
    selectedPartIds,
    hoveredListReferenceId,
    hoveredModelReferenceId,
    hoveredListPartId,
    hoveredModelPartId
  });

  // The Reference pane shows every selected element: topology references
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
    if (stepInteractionBlocked) {
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
  // What the tool in hand may pick: Measure snaps to what its own filter says, Select to what
  // the selection filter allows.
  const viewerPickableFacesForTool = measureModeActive
    ? (["all", "faces"].includes(measureSelectionFilter) ? viewerPickableFaces : EMPTY_LIST) : filteredViewerFaces;
  const viewerPickableEdgesForTool = measureModeActive
    ? (["all", "edges"].includes(measureSelectionFilter) ? viewerPickableEdges : EMPTY_LIST) : filteredViewerEdges;
  const viewerPickableVerticesForTool = (measureModeActive
    ? ["all", "points"].includes(measureSelectionFilter) : selectionFilter === "all") ? viewerPickableVertices : EMPTY_LIST;
  const measureToolDisabled = viewerLoading || !selectedMeshData || !supportsMeasure;
  const topologySelectionActive =
    (isAssemblyView && requestedStepTreeTopologyNodeIds.length > 0) ||
    topLevelReferenceSelectionActive;
  const referenceSelectionUnavailable = (
    isStepEntry &&
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
    isStepEntry &&
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
  const promptResource = useMemo(() => ({ ...documentResource,
    revision: String(selectedEntry?.documentHash || selectedEntry?.hash || documentResource.revision || '')
  }), [documentResource, selectedEntry?.documentHash, selectedEntry?.hash]);
  // Rebuilds keep the previous same-file mesh visible until its replacement is
  // ready. Observe that mesh's document revision while interaction is blocked.
  const displayedResourceRef = useRef(promptResource);
  if (!retainingPreviousStepMesh) displayedResourceRef.current = promptResource;
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
    resetModel: resetStepMotion,
    // The kit's playbar reads its time from the runtime it is handed, not from a context: the
    // old STEP-only bar did, which is why this object never carried one. It is the same clock
    // the pose pass writes per frame, so the scrubber re-renders and nothing else does.
    clock: animationClock
  };
  // Only a STEP carries routines here; every other format this renderer shows has none.
  const viewportAnimation = selectedFileSheetKind === "step" ? stepAnimationControls : null;
  // Animate is one mode with two ways in: the tool, and fullscreen, which is that
  // tool with the rest of the viewer put away (or no tool, without animation).
  const animationAvailable = animationControlsHaveContent(viewportAnimation);
  const animateToolActive = !previewMode && animationAvailable && tabToolMode === TAB_TOOL_MODE.ANIMATE;
  const animateModeActive = animationAvailable && (previewMode || animateToolActive);
  // A routine owns the model's pose only inside the mode. Outside it the clip is
  // released — stopped, rewound, the pose back with Position — so selection,
  // topology and Position never meet an animated model and need no special case
  // for one. Nothing of the playback survives: coming back starts from the start,
  // and a restored session that was mid-routine is released the same way.
  const releaseAnimation = selectedFileSheetKind === "step" ? releaseStepAnimation : null;
  const animationOwnsPose = animationAvailable && viewportAnimation?.enabled !== false;

  // Pose: drag the joints by their handles. Present only where something can be
  // driven (a STEP's mate DOFs). The handles are rebuilt from the pose on screen,
  // so sliders, presets, Reset and a handle up the chain all carry them along.
  const stepPoseDefinition = selectedFileSheetKind === "step" ? selectedStepParameterRuntime?.definition || null : null;
  const poseAvailable = stepPosableDofs(stepPoseDefinition).length > 0;
  const poseToolActive = !previewMode && poseAvailable && tabToolMode === TAB_TOOL_MODE.POSE;

  const shellRef = useRef(null);
  // The two things only a STEP can answer about its viewport. Both read the live runtime's own
  // scene graph, so neither can live on the kit's handle: the LOD sampler reports projection
  // parameters and nearest eligible occurrence distances (numeric samples retain no scene
  // objects), and the selection's bounds are the boxes of its references AS POSED merged with
  // the boxes of its parts as they sit on screen, explosion included.
  const zoomToFitSelection = useCallback(({ partIds = [], referenceIds = [], animate = true } = {}) => {
    const runtime = runtimeRefRef.current?.current;
    const bounds = mergeBoundsList([
      selectorReferenceBounds(layersApiRef.current?.activeSelectorRuntime, referenceIds),
      displayRecordBoundsForPartIds(runtime, partIds)
    ]);
    return bounds ? Boolean(viewerRef.current?.zoomToBounds(bounds, { animate })) : false;
  }, []);

  // ---- what the viewport is, before the shell mounts one ------------------------------------
  // The STEP scene is one object for as long as this file is open; what is INSIDE it changes in
  // place. The viewport is handed a view of it only once there is geometry to look at.
  const keepsAuthoredFinish = useMemo(() => hasAuthoredMaterials(selectedDisplayMeshData), [selectedDisplayMeshData]);
  const sceneView = useMemo(() => stepSceneView(stepScene, keepsAuthoredFinish), [stepScene, keepsAuthoredFinish]);
  const viewportIsLoading = viewerLoading && !retainingPreviousStepMesh;
  const viewportScene = !viewportIsLoading && hasMeshGeometry(selectedDisplayMeshData) ? sceneView : null;
  // The WebGL runtime under the scene. A scene owns GPU-backed work the LOD publisher is counting
  // on, so every way a runtime can go away is named to it exactly once — and this is that place.
  const meshSourceAdoptionRef = useRef(onMeshSourceAdoption);
  meshSourceAdoptionRef.current = onMeshSourceAdoption;
  const stepRuntimeLifecycle = useMemo(() => ({
    onRelease(runtime, { handoff }) {
      const source = releaseStepRuntime(runtime, stepScene);
      meshSourceAdoptionRef.current?.(source, false, { disposed: true, terminal: !handoff, handoff });
    },
    onContextLost() { meshSourceAdoptionRef.current?.(null, false); },
    // A replacement runtime that cannot initialize has no future scene that can finish an
    // in-flight LOD handoff.
    onInitializationError() { meshSourceAdoptionRef.current?.(null, false, { disposed: true, terminal: true }); }
  }), [stepScene]);
  const viewPolicy = { wireframeMode: viewDrawsHairlines(resolvedThemeSettings, resolvedScene.display), edgesVisible: false };

  // ---- the live surface, the prompt and Escape, as stable seams -------------------------------
  // Each of these is answered from further down this function, where the selection, the tree and
  // the menus are. They are bound through refs so the shell sees one unchanging set of commands,
  // and every one of them reads the view as it stands when it is CALLED.
  const stepLiveStateRef = useRef(() => ({}));
  const stepLiveCommandsRef = useRef({});
  const stepLiveCommands = useMemo(() => Object.fromEntries(
    ["select", "clearSelection"].map(name => [name, (...args) => stepLiveCommandsRef.current[name]?.(...args)])
  ), []);
  const promptReferencesRef = useRef(() => EMPTY_LIST);
  const escapeRef = useRef(() => false);
  // Escape has something to do here whenever there is a selection to clear or a Measure session
  // to leave; an open panel is the shell's own reason.
  const escapeActive = selectedPartIds.length > 0 || selectedReferenceIds.length > 0 || focusedAssemblyNodeIds.length > 0
    || tabToolMode === TAB_TOOL_MODE.MEASURE;


  // ---- the shell --------------------------------------------------------------------------
  // Everything this renderer needs from its host that is not about its scene. It is called
  // HERE, in the middle of this function, and not at the top: the hook needs a load report,
  // and what this renderer's load IS depends on the resolved view above it. Nothing about
  // hook order says otherwise — there is one function, and no early return in it.
  const shell = useRendererShell({
    view, services, resource: promptResource, modelKey: selectedKey, revisionKey: presentationRevisionKey,
    features: viewFeatures, toolModes: CAD_TOOL_MODES, tool: { mode: tabToolMode, set: setTabToolMode },
    scene: viewportScene,
    viewSettings: { display: displaySettings, scene: desiredScene, store: viewSettingsStore, applied: viewUpdate },
    viewerRef,
    load: {
      // `busy` is the shell's "nothing to show yet", and the viewport DETACHES the scene while
      // it is true. So it is exactly the gate the old STEP viewport kept: loading, and not
      // holding the previous revision on screen. A model arriving in pieces, a rebuild behind a
      // retained mesh and an artifact still generating all have something to show — they are
      // `updating`, which keeps the chip saying so without taking the model off the screen.
      busy: viewportIsLoading,
      updating: !viewportIsLoading && (effectiveViewerLoading || selectedMeshPartial),
      progress: selectedLoadProgress || (editingPreview.state.phase ? { phase: editingPreview.state.phase, detail: editingPreview.state.detail } : null),
      alert: viewerAlert || (!selectedMeshData && catalogError ? catalogError : null),
      editPending: ["submitted", "queued", "building"].includes(editingPreview.state?.state) && !editingPreview.state?.saved,
      currentPreview: currentPreviewVisible,
      finding: !catalogHydrated || selectedCatalogPending
    },
    // The playbar belongs to the Animate mode here, not to every file with routines: a STEP
    // takes Animate UP, and leaving it puts the model back at rest.
    animation: animateModeActive ? viewportAnimation : null,
    live: {
      commands: stepLiveCommands,
      // What the viewport is SHOWING, which is not always what is loading: a rebuild that
      // keeps its predecessor on screen reports the predecessor's revision.
      resource: () => displayedResourceRef.current,
      state: () => stepLiveStateRef.current()
    },
    promptReferences: () => promptReferencesRef.current(),
    promptContext: createCadPromptContext,
    escape: { active: escapeActive, handle: () => escapeRef.current() },
    rendererState,
    toolRestore: CAD_TOOL_RESTORE,
    displayProps: {
      edgeStatus: displayEdgeStatus,
      edgeError: displayEdgeError
    },
    onCameraSettled: () => onLodCameraMoved(),
    preserveInteractionPixelRatio: viewPolicy.wireframeMode || viewPolicy.edgesVisible,
    runtimeLifecycle: stepRuntimeLifecycle,
    onRuntimeAlert: handleViewerAlertChange,
    onPresentationChange: handlePresentationChange
  });
  shellRef.current = shell;
  const setCopyStatus = shell.setCopyStatus;
  const setScreenshotStatus = shell.setScreenshotStatus;
  const filePanelOpen = shell.openPanel === CAD_PANEL.file;

  useEffect(() => {
    if (!animationAvailable && shellRef.current?.toolMode === TAB_TOOL_MODE.ANIMATE) shellRef.current.selectTool(TAB_TOOL_MODE.REFERENCES);
  }, [animationAvailable]);
  useEffect(() => {
    if (!poseAvailable && shellRef.current?.toolMode === TAB_TOOL_MODE.POSE) shellRef.current.selectTool(TAB_TOOL_MODE.REFERENCES);
  }, [poseAvailable]);
  useEffect(() => {
    if (!animateModeActive && animationOwnsPose) releaseAnimation?.();
  }, [animateModeActive, animationOwnsPose, releaseAnimation]);
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
    // Something in the viewport has details in the tree: show this file's panel.
    shellRef.current?.revealFilePanel();
    if (expandAncestors || expandSelf || source === "reference") {
      expandStepTreeAroundNode(normalizedNodeId, { expandSelf });
    }
  }, [
    expandStepTreeAroundNode,
    selectedFileSheetKind
  ]);

  const ensureSelectTool = useCallback(() => {
    if (shellRef.current?.toolMode !== TAB_TOOL_MODE.REFERENCES) shellRef.current?.selectTool(TAB_TOOL_MODE.REFERENCES);
  }, []);

  const toggleReferenceSelection = useCallback((referenceId, { multiSelect = false, source = "viewer" } = {}) => {
    if (stepInteractionBlocked) {
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
    isAssemblyView,
    referencePartId,
    revealStepTreeNode,
    stepInteractionBlocked,
  ]);

  const clearReferenceSelection = useCallback(() => {
    selectedReferenceIdsRef.current = [];
    setSelectedWholeEntryCadRefToken("");
    setSelectedReferenceIds([]);
    setCopyStatus("");
  }, []);

  // Copy is clipboard-only. Adding context is an explicit host action.
  const deliverReferenceText = useCallback((text) => host.clipboard.writeText(text), [host.clipboard]);
  const showPromptResult = useCallback((result) => shellRef.current?.setCopyStatus(promptDeliveryMessage(result)), []);
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
    if (stepInteractionBlocked) {
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
    isAssemblyView,
    focusedAssemblyNodeIds,
    removeSelectedAssemblyNode,
    revealStepTreeNode,
    renderPartIdForAssemblySelection,
    validAssemblySelectionIdSet,
    viewerSelectableAssemblyNodeIdSet,
    stepInteractionBlocked,
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
    {
      return;
    }
    if (
      selectedPartIdsRef.current.length ||
      selectedReferenceIdsRef.current.length ||
      selectedWholeEntryCadRefToken
    ) {
      clearAssemblySelection();
    }
  }, [clearAssemblySelection, selectedWholeEntryCadRefToken]);

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
    if (stepInteractionBlocked) {
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
  ]);

  const tangentFaces = useMemo(() => buildTangentFaceGraph(
    selectionFilter === "tangent-faces" ? [...effectiveActiveReferenceMap.values()] : EMPTY_LIST
  ), [selectionFilter, effectiveActiveReferenceMap]);

  const edgeChains = useMemo(() => buildEdgeChainGraph(
    selectionFilter === "edge-chain" ? [...effectiveActiveReferenceMap.values()] : EMPTY_LIST
  ), [selectionFilter, effectiveActiveReferenceMap]);

  const handleModelReferenceActivate = useCallback((referenceId, { multiSelect = false } = {}) => {
    if (stepInteractionBlocked) {
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
    if (selectedEntry && isStepEntry) {
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
  ]);

  const handleModelReferenceDoubleActivate = useCallback((referenceId) => {
    if (stepInteractionBlocked || !isAssemblyView) {
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

  /**
   * The menu over topology: the faces and edges of one pick in the viewport, or of one
   * Features row (its feature, group or body). It is one descriptor for both, so the tree's
   * menu over a feature is the viewport's over its faces. Topology is not a part, so it offers
   * no isolate or visibility; its actions take the selection with it, as a part's do.
   *
   * `referenceIds` may be empty while a row's topology is still loading: the menu then opens
   * with nothing to copy yet, rather than not at all.
   */
  const topologyReferenceMenu = useCallback((referenceIds, label = "") => {
    const ids = uniqueStringList(
      (Array.isArray(referenceIds) ? referenceIds : []).map((id) => String(id || "").trim()).filter(Boolean)
    );
    const selectedContextReferenceIds = uniqueStringList(
      selectedReferenceIdsRef.current
        .map((id) => String(id || "").trim())
        .filter(Boolean)
    );
    const actionReferenceIds = ids.length ? uniqueStringList([...selectedContextReferenceIds, ...ids]) : [];
    const referencesForCopy = actionReferenceIds
      .map((id) => (
        stepTreeCopyReferenceMap.get(id) ||
        effectiveActiveReferenceMap.get(id) ||
        copyReferenceForRawSelectorSelection(id, "topology")
      ))
      .filter(Boolean);
    const { lines } = actionReferenceIds.length ? copyPayloadWithSelectedIdFallback(buildSelectionCopyPayload({
      references: referencesForCopy,
      parts: [],
      entry: selectedEntry
    }), {
      selectedReferenceIds: actionReferenceIds,
      copyReferenceMap: stepTreeCopyReferenceMap
    }) : { lines: [] };
    return {
      referenceId: ids[0] || "",
      referenceIds: actionReferenceIds,
      label: String(label || ids[0] || "").trim(),
      selected: ids.length > 0 && ids.every((id) => selectedContextReferenceIds.includes(id)),
      hidden: false,
      focused: false,
      actionCount: actionReferenceIds.length || 1,
      copyText: lines.join("\n"),
      zoomSelectionAvailable: zoomSelectionRef.current.available,
      showIsolate: false,
      showHideOther: false,
      showVisibility: false,
      showHideAll: false
    };
  }, [
    effectiveActiveReferenceMap,
    selectedEntry,
    stepTreeCopyReferenceMap
  ]);

  // Only ever reached under Select (the viewport's menu is offered by that tool alone), so
  // nothing it offers can contradict the tool.
  const handleModelReferenceContext = useCallback((referenceId, { clientX = 0, clientY = 0 } = {}) => {
    if (stepInteractionBlocked) {
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
      setViewerContextMenu({
        x: Number(clientX) || 0,
        y: Number(clientY) || 0,
        ...topologyReferenceMenu(
          [pickedPartId],
          topologyReference?.label || topologyReference?.displayName || pickedPartId
        )
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
    stepInteractionBlocked,
    topologyReferenceMenu,
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
      || !zoomToFitSelection({ partIds, referenceIds, animate: true })) {
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

  const handleSelectTabToolMode = useCallback((mode) => {
    // Measure and Draw are sessions: asking for the active one again ends it, which is the
    // shell's state machine. (The Measure button spends its second press on the snap menu.)
    shellRef.current?.selectTool(mode);
    const normalizedMode = CAD_TOOL_MODES.normalize(mode);
    if (
      selectedEntry &&
      selectedEntryHasReferences &&
      normalizedMode === TAB_TOOL_MODE.MEASURE && topologyTarget
    ) {
      loadFilterTopology(topologyTarget);
    }
  }, [selectedEntry, selectedEntryHasReferences, topologyTarget, loadFilterTopology]);

  // An inspection highlight is a narrower selection than the tree's, and is what the
  // person is actually looking at, so it wins.
  const zoomSelectionPartIds = inspectionHighlight ? inspectionHighlight.partIds || EMPTY_LIST : viewerSelectedPartIds;
  const zoomSelectionReferenceIds = inspectionHighlight ? inspectionHighlight.faceIds || EMPTY_LIST : selectedReferenceIds;
  zoomSelectionRef.current = {
    partIds: zoomSelectionPartIds,
    referenceIds: zoomSelectionReferenceIds,
    available: Boolean(zoomSelectionPartIds.length || zoomSelectionReferenceIds.length)
  };

  // What Escape means in this renderer, innermost first: a measurement in progress, then
  // the Measure tool, then the selection. An open panel is the shell's.
  escapeRef.current = () => {
    if (!previewMode && tabToolMode === TAB_TOOL_MODE.MEASURE) {
      // Escape cancels the measurement in progress and leaves the tool armed, the way it does
      // in a CAD measure tool. Only once there is nothing to cancel does it leave the tool.
      if (measureRulerState?.draft?.anchor) handleMeasureCancelDraft();
      else shellRef.current?.selectTool(TAB_TOOL_MODE.REFERENCES);
      return true;
    }
    if (selectedPartIds.length > 0 || selectedReferenceIds.length > 0) { clearAssemblySelection(); return true; }
    // Then isolation: Escape backs out one layer at a time, selection first.
    if (focusedAssemblyNodeIds.length > 0) { handleExitIsolate(); return true; }
    return false;
  };

  // ---- the live surface ---------------------------------------------------------------------
  // App tools bind to this actual mounted viewport, never catalog metadata. The shell owns the
  // binding; these are the fields and commands only a STEP has.
  stepLiveStateRef.current = () => {
    const displayedResource = displayedResourceRef.current;
    return {
      // The selection in the PROMPT grammar, as the live contract reads it: the references a
      // snapshot would carry, each a selector of (or the whole of) the document on screen.
      // `promptReferencesRef` holds them in this renderer's own vocabulary, which only
      // `createCadPromptContext` speaks.
      selection: promptReferencesRef.current().map(reference => ({
        resource: { ...displayedResource },
        target: reference.selector ? { kind: 'cad-selector', selectors: reference.selector.split(',') } : { kind: 'whole-resource' },
        ...(reference.label ? { label: reference.label } : {})
      })),
      loading: Boolean(viewerLoading || stepInteractionBlocked),
      selectedPartIds: [...(inspectionHighlight ? inspectionHighlight.partIds || [] : viewerSelectedPartIds)],
      selectedReferenceIds: [...(inspectionHighlight ? inspectionHighlight.faceIds || [] : selectedReferenceIdsRef.current)],
      hiddenPartIds: [...hiddenPartIds], isolatedPartIds: [...isolatedAssemblyNodeIds],
      resource: { ...displayedResource }, revision: String(displayedResource.revision || '')
    };
  };
  // What a snapshot depicts: the references the selection resolves to, in this renderer's own
  // vocabulary (`createCadPromptContext` speaks it).
  promptReferencesRef.current = () => referencesForHost(inspectionHighlight ? stepGeometryPromptText(inspectionHighlight, {
    referenceMap: effectiveActiveReferenceMap, parts: selectedMeshData?.parts || EMPTY_LIST, entry: selectedEntry,
  }) : canonicalCopySelectionLines.join("\n"));
  stepLiveCommandsRef.current = {
    select({ selectors, replace = true }) {
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
    }
  };

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
  // Every CAD format shares the View settings and camera contract.
  const renderDisplaySettings = resolvedScene.display;

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

  // ---- the viewport ---------------------------------------------------------------------------
  // What the viewport is ALLOWED to show and pick just now: nothing of the model under Pose,
  // Animate or fullscreen; no topology while a previous mesh is held over an update.
  const holdingPreviousMesh = retainingPreviousStepMesh;
  const topologySelectionDeferred = Boolean(selectedTopologyDeferredByCost && selectedMeshData);
  // Animate, like fullscreen, is watching, and Pose offers its knobs alone.
  const watching = previewMode || animateToolActive || Boolean(jointHandles);
  const pickMode = watching || holdingPreviousMesh ? VIEWER_PICK_MODE.NONE : viewerPickModeForRenderPane({
    selectionFilter,
    topologySelectionPending: referenceSelectionPending,
    topologySelectionUnavailable: referenceSelectionUnavailable,
    topologySelectionDeferred,
    topologyPickingActive: Boolean(viewerPickableFacesForTool?.length || viewerPickableEdgesForTool?.length || viewerPickableVerticesForTool?.length),
    viewerMode,
    assemblyPickingActive: viewerInAssemblyMode,
    focusedPartIds: viewerFocusedPartIds,
    measureMode: measureModeActive
  });
  // One shared empty list: a fresh [] per render — per animation frame — invalidated the
  // layers' pickable memos and reference map.
  const pickable = list => (!holdingPreviousMesh && !watching ? list : EMPTY_LIST);
  // Part-state lists pass through by IDENTITY: what reaches the layers is already stable for as
  // long as its contents hold, because every one of them is derived through a memo above.
  const layerProps = {
    meshData: selectedDisplayMeshData,
    modelKey: selectedKey,
    isLoading: viewportIsLoading,
    renderMode: resolvedScene.render.enabled,
    renderConfiguration: resolvedScene.render.configuration,
    appearance: resolvedScene.appearance,
    materialOverrides: resolvedMaterialOverrides,
    receiveShadows: resolvedScene.view.lighting.enabled,
    previewMode,
    pickMode,
    pickableParts: !holdingPreviousMesh ? viewerAssemblyRenderParts : EMPTY_LIST,
    hiddenPartIds: viewerHiddenPartIdsForRenderPane({ inspectionEnabled: true, hasParts: true, hiddenPartIds: viewerHiddenPartIds }),
    selectedPartIds: previewMode ? EMPTY_LIST : viewerSelectedPartIdsForRenderPane({ renderMode: resolvedScene.render.enabled, hasParts: true,
      selectedPartIds: inspectionHighlight ? inspectionHighlight.partIds || EMPTY_LIST : viewerSelectedPartIds }),
    hoveredPartId: !previewMode ? viewerHoveredPartIds : "",
    hoveredReferenceId: !previewMode && !holdingPreviousMesh ? effectiveHoveredReferenceId : "",
    selectedReferenceIds: !previewMode && !holdingPreviousMesh
      ? (inspectionHighlight ? inspectionHighlight.faceIds || EMPTY_LIST : selectedReferenceIds) : EMPTY_LIST,
    selectorRuntime: viewerSelectorRuntimeForRenderPane({ renderMode: resolvedScene.render.enabled, hasTopology: true,
      retainingPreviousStepMesh: holdingPreviousMesh, selectorRuntime: effectiveSelectorRuntime }),
    displayEdgeRuntime: !holdingPreviousMesh ? selectedDisplayEdgeRuntime : null,
    stepParameterRuntime: selectedStepParameterRuntime,
    // {clip, elapsedSec, playing} or null. Null means no clip is selected, and the evaluator never runs.
    stepAnimationRuntime: selectedAnimationRuntime,
    animateMode: previewMode || animateToolActive,
    jointHandles: previewMode ? null : jointHandles,
    measureState: inspectionHighlight?.measurement ? { measurements: [inspectionHighlight.measurement] } : measureRulerState,
    activeMeasurementId: inspectionHighlight?.measurement?.id || activeMeasureId,
    measureModeActive: !previewMode && measureModeActive,
    allowMeshVertexSnap: false,
    onLodCameraChange: onLodCameraMoved,
    onMeshSourceAdoption: handleDisplayMeshAdoption,
    onViewerAlertChange: handleViewerAlertChange,
    onStepModuleTransformDetectedChange: handleStepModuleTransformDetectedChange,
    onHoverReferenceChange: !previewMode ? handleModelHoverChange : null,
    onActivateReference: !previewMode ? handleModelReferenceActivate : null,
    onDoubleActivateReference: !previewMode ? handleModelReferenceDoubleActivate : null,
    onMeasurePick: !previewMode ? handleMeasurePick : null,
    onMeasureHoverPoint: !previewMode ? handleMeasureHoverPoint : null,
    pickAtRef
  };
  const viewPolicyResolved = useStepViewPolicy({
    meshData: selectedDisplayMeshData, themeSettings: resolvedThemeSettings, displaySettings: renderDisplaySettings,
    renderMode: resolvedScene.render.enabled, renderConfiguration: resolvedScene.render.configuration,
    renderPartsIndividually: Boolean(selectedStepParameterRuntime) || Boolean(selectedAnimationRuntime) ||
      Boolean(Object.keys(selectedDisplayMeshData?.appearance?.materials || {}).length) ||
      Boolean(selectedStepParameterRuntime?.definition) || Boolean(selectedAnimationRuntime?.clip),
    pickMode, pickableParts: layerProps.pickableParts,
    pickableFaces: pickable(viewerPickableFacesForTool), pickableEdges: pickable(viewerPickableEdgesForTool),
    pickableVertices: pickable(viewerPickableVerticesForTool),
    hiddenPartIds: layerProps.hiddenPartIds, selectedPartIds: layerProps.selectedPartIds,
    focusedPartId: viewerFocusedPartIds
  });
  lodSelectedPartIdsRef.current = layerProps.selectedPartIds;

  // ---- the strip ------------------------------------------------------------------------------
  const selectDisabled = viewerLoading || !selectedMeshData || referenceSelectionPending ||
    referenceSelectionUnavailable || topologySelectionDeferred;
  const toolIdle = viewerLoading || !selectedMeshData;
  // In an assembly, faces and edges load for one part at a time (topologyTarget). With a face
  // or edge filter and no part chosen, a click has nothing to pick; say why instead of silence.
  const topologyFilterHint = isAssemblyView && !topologyTarget && TOPOLOGY_FILTER_NOUNS[selectionFilter]
    ? `Select a part to pick its ${TOPOLOGY_FILTER_NOUNS[selectionFilter]}` : "";
  const viewToggle = ({ id, group, label, Icon, disabled, panel }) => {
    const on = desiredScene.view[group]?.enabled === true;
    return { id, label, active: !previewMode && on, disabled: toolIdle || disabled,
      icon: <Icon className="size-3" strokeWidth={2} aria-hidden="true" />,
      onSelect: () => viewSettingsStore.setEnabled(group, !on),
      subToolbar: on && !previewMode ? <ViewToolPanel title={label}>{panel}</ViewToolPanel> : null };
  };
  const viewToggles = [
    viewFeatures.sections.includes("exploded") ? viewToggle({ id: "explode", group: "exploded", label: "Explode", Icon: UnfoldVertical,
      disabled: explodablePartCount(selectedMeshData) <= 1,
      panel: <ExplodeControls viewSettings={displaySettings} onViewSettingsPatch={viewSettingsStore.patch} /> }) : null,
    viewFeatures.sections.includes("clip") ? viewToggle({ id: "cross-section", group: "clip", label: "Cross-section", Icon: SquareSplitHorizontal,
      panel: <CrossSectionControls viewSettings={displaySettings} onViewSettingsPatch={viewSettingsStore.patch} bounds={selectedMeshData?.bounds || null} /> }) : null
  ].filter(Boolean);
  const tools = [
    supportsTool(selectedEntrySourceFormat, "select") ? shell.tools.own({
      id: TAB_TOOL_MODE.REFERENCES,
      label: referenceSelectionPending ? "Preparing selection" : "Select",
      icon: <MousePointer2 className="size-3" strokeWidth={2} aria-hidden="true" />,
      active: !topologySelectionDeferred && selectionToolActive, disabled: selectDisabled,
      description: supportsTopology ? "Select again to choose a selection filter" : undefined,
      secondPressOpensMenu: true,
      onSelect: () => handleSelectTabToolMode(TAB_TOOL_MODE.REFERENCES),
      menu: supportsTopology ? trigger => <SelectionFilterMenu value={selectionFilter} trigger={trigger}
        onChange={value => { setSelectionFilter(value); handleSelectTabToolMode(TAB_TOOL_MODE.REFERENCES); }} /> : undefined,
      subToolbar: <ToolFilterNote options={supportsTopology ? SELECTION_FILTERS : null} value={supportsTopology ? selectionFilter : null}
        active={selectionToolActive} notice={selectionFilterNotice || topologyFilterHint} />
    }) : null,
    // Measure works like Select: the first press takes up the tool, a press while it is active
    // opens what it snaps to. It does not toggle off; another tool or Escape ends the session.
    supportsMeasure ? shell.tools.own({
      id: TAB_TOOL_MODE.MEASURE, label: "Measure",
      icon: <Ruler className="size-3" strokeWidth={2} aria-hidden="true" />,
      active: measureModeActive, disabled: toolIdle || measureToolDisabled,
      description: supportsTopology ? "Measure again to choose what measurements snap to" : undefined,
      secondPressOpensMenu: true,
      onSelect: () => { if (!measureModeActive || !supportsTopology) handleSelectTabToolMode(TAB_TOOL_MODE.MEASURE); },
      menu: supportsTopology ? trigger => <SelectionFilterMenu options={MEASURE_SELECTION_FILTERS} menuLabel="Snap to" hint=""
        value={measureSelectionFilter} trigger={trigger} onChange={value => {
          setMeasureSelectionFilter(value); handleMeasureCancelDraft();
          if (topologyTarget) loadFilterTopology(topologyTarget);
        }} /> : undefined,
      subToolbar: <ToolFilterNote options={supportsTopology ? MEASURE_SELECTION_FILTERS : null}
        value={supportsTopology ? measureSelectionFilter : null} active={measureModeActive}
        panel={<MeasurePanel measurements={measureMeasurements} activeId={activeMeasureId}
          onActivate={setActiveMeasureId} onDelete={handleMeasureDelete} onClear={handleMeasureClear} />} />
    }) : null,
    // Explode and Cross-section examine the design, like Measure, but they are toggles and not
    // tools: tools are one at a time, and a person selects or measures while exploded or cut.
    // A press turns one on or off; while on, its controls sit in a panel under the strip.
    ...viewToggles,
    supportsTool(selectedEntrySourceFormat, "draw") ? { ...shell.tools.draw, disabled: toolIdle } : null,
    // Only in a file with joints to drag (never a disabled button). It sits with Animate,
    // the other tool that moves the model.
    poseAvailable ? shell.tools.own({ id: TAB_TOOL_MODE.POSE, label: "Position",
      icon: <SplinePointer className="size-3" strokeWidth={2} aria-hidden="true" />,
      active: poseToolActive, disabled: toolIdle, onSelect: () => handleSelectTabToolMode(TAB_TOOL_MODE.POSE) }) : null,
    // Last of the model's own tools, and only in a file that has routines: no routines, no button. Its controls
    // are the playbar, under the model while the tool is up.
    animationAvailable ? shell.tools.own({ id: TAB_TOOL_MODE.ANIMATE, label: "Animate",
      icon: <CirclePlay className="size-3" strokeWidth={2} aria-hidden="true" />,
      active: animateToolActive, disabled: toolIdle, onSelect: () => handleSelectTabToolMode(TAB_TOOL_MODE.ANIMATE) }) : null,
    // Last of all, and only where the host offers one: fullscreen is an act on the view, not a
    // tool to be in, and a STEP is the one file that presents itself there.
    shell.tools.fullscreen
  ].filter(Boolean);

  // ---- the bottom action ----------------------------------------------------------------------
  const selectionActionVisible = selectionCount > 0 && !stepUpdateInProgress && !referenceSelectionPending
    && !referenceSelectionUnavailable && !topologySelectionDeferred;
  const bottomAction = drawToolActive
    ? (stepUpdateInProgress || referenceSelectionPending || referenceSelectionUnavailable || topologySelectionDeferred ? null : undefined)
    : selectionActionVisible ? {
      // A reference cut off mid-token reads like a broken reference, so a long one becomes a count.
      label: composerDestination ? "Add to prompt" : copyButtonLabel,
      shortLabel: composerDestination ? "" : copyButtonCountLabel,
      render: ({ className, disabled, title, children }) => (
        <PromptContextAction type="button" variant="default" size="sm" className={className} disabled={disabled}
          createContext={createSelectionPromptContext} onResult={showPromptResult} title={title}>{children}</PromptContextAction>
      ),
      children: slots?.selectionExtras && selectionCount > 0 && !viewerLoading && !stepInteractionBlocked ? <slots.selectionExtras
        selection={Object.freeze(createSelectionPromptContext().parts.filter(part => part.kind === 'reference').map(part => part.reference))}
        selectionKey={selectionKey}
        disabled={viewerLoading || stepInteractionBlocked || !promptAvailable}
        createContext={createSelectionPromptContext}
      /> : null
    } : null;

  // ---- the file's panel ------------------------------------------------------------------------
  const stepPanel = useStepPanel({
    selectedMeshData: selectedDisplayMeshData,
    selectedSourceAppearance,
    client,
    geometryInspection: { file: selectedEntry?.file, revision: artifactRevision,
      references: !viewerLoading && !stepUpdateInProgress ? isAssemblyView ? assemblyStepTreeTopologyReferences : selectedSelectorRuntime?.references || EMPTY_LIST : EMPTY_LIST,
      parts: !viewerLoading && !stepUpdateInProgress ? selectedMeshData?.parts || EMPTY_LIST : EMPTY_LIST,
      onHighlight: handleInspectionHighlight, onLoadTopology: loadInspectionTopology },
    open: filePanelOpen && !previewMode,
    selectedEntry,
    viewerLoading: viewerLoading || assemblySidebarLoading,
    isAssemblyView,
    stepTreeRoot: displayStepTreeRoot,
    expandedTreeNodeIds: expandedStepTreeNodeIds,
    onVisibleFeatureTargetsChange: handleVisibleFeatureTargetsChange,
    selectedPartIds,
    selectedReferenceIds,
    selectedReferences: selectedReferenceItems,
    selectableNodeIds: isolatedStepTreeSelectableNodeIds,
    activeTreeNodeScrollKey,
    hiddenPartIds,
    focusedNodeIds: focusedAssemblyNodeIds,
    onSelectTreeNode: selectStepTreeNode,
    onSelectReferenceGroup: selectReferenceGroup,
    onCopyTreeNodeReference: copyStepTreeContextMenuReference,
    onFocusTreeNode: focusStepTreeNode,
    onUnfocusTreeNode: handleExitSingleIsolate,
    onExitAllIsolate: handleExitIsolate,
    onToggleTreeNode: toggleStepTreeNode,
    onClearSelection: clearAssemblySelection,
    onHoverTreeNode: setHoveredListPartId,
    onTogglePartVisibility: togglePartVisibility,
    treeSelectionDisabled: stepInteractionBlocked,
    menuForNode: assemblyNodeMenu,
    menuForReferences: topologyReferenceMenu,
    partMenuActions,
    showAllHiddenParts: handleShowAllHiddenParts,
    stepModule: stepPositionControls,
    stepAnimation: stepAnimationControls,
    statusItems: selectedFileStatusItems
  });

  return <RendererShell shell={shell} tools={tools} panel={stepPanel}
    className={className}
    bottomAction={bottomAction}
    contextMenuItems={selectionToolActive
      ? press => viewportContextMenuItems(press, pickAtRef.current?.(press.clientX, press.clientY) || "") : null}
    onContextMenuOpenChange={handleViewportContextMenuOpenChange}
    // A press on the model puts the inspection highlight down: what the person is looking at
    // is what they just pointed at.
    onCanvasPointerDown={() => setInspectionHighlight(null)}
    // Both halves read it: the viewport's menu resolves references through it, and so do the
    // panel's rows, which are portaled out of this tree into the host's panel column.
    frameProvider={frame => <HostReferenceContext.Provider value={hostReference}>{frame}</HostReferenceContext.Provider>}
    viewportOverlay={viewport => {
      runtimeRefRef.current = viewport.runtimeRef;
      return <StepSceneLayers viewport={viewport} stepScene={stepScene} policy={viewPolicyResolved} props={layerProps} api={layersApiRef} />;
    }} />;
}

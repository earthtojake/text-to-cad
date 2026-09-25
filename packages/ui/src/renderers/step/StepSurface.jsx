import { buildEdgeChainGraph } from "./workbench/edgeChainSelection.js";
"use client";

import SelectionFilterMenu, { ToolFilterNote } from "./components/workbench/SelectionFilterMenu.jsx";
import { MEASURE_SELECTION_FILTERS, SELECTION_FILTERS } from "./workbench/selectionFilter.js";
import { Play, MousePointer2, Ruler, Spline } from "lucide-react";
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
import RendererShell from "../kit/shell/RendererShell.jsx";
import { presentationIsPending, usePresentationReport, usePresentationState, useRendererShell } from "../kit/shell/useRendererShell.js";
import { readShellState, shellPresentationKey } from "../kit/shell/shellState.js";
import StepSceneLayers, { releaseStepRuntime } from "./scene/StepSceneLayers.jsx";
import { displayRecordExplodedViewTranslation } from "./scene/useStepExplode.js";
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
import { ALL_VIEW_FEATURES } from "@hardcore/core/common/viewSettings.js";
import { useModelTools } from "./components/workbench/ModelTools.jsx";
import { useStepPanel } from "./components/workbench/StepPanel.js";
import { CAD_PANEL } from "../../file-viewer/navigation/panels.js";
import { stepMotionSources, useStepMotion } from "./workbench/useStepMotion.js";
import { animationControlsHaveContent } from "../kit/tools/playbar/ViewportAnimationBar.js";
import { useCadAssets } from "./components/workbench/hooks/useCadAssets.js";
import { useEditingPreview } from "./components/workbench/hooks/useEditingPreview.js";
import { useViewportQualityStatus } from "./components/workbench/hooks/useViewportQualityStatus.js";
import { previewGeometryChanged } from "./workbench/editingPreview.js";
import MeasurePanel from "./components/workbench/MeasurePanel.jsx";
import { useCadWorkspaceSelection } from "./components/workbench/hooks/useCadWorkspaceSelection.js";
import { useCadWorkspaceSelectors } from "./components/workbench/hooks/useCadWorkspaceSelectors.js";
import { useAppliedViewSettings } from "../kit/view-settings/useAppliedViewSettings.js";
import { useViewSettings } from "../kit/view-settings/useViewSettings.js";
import { presentationDisplaySettings } from "../kit/view-settings/viewerDisplaySettings.js";
import {
  ASSET_STATUS,
  CAD_TOOL_MODES,
  CAD_TOOL_RESTORE,
  REFERENCE_STATUS,
  TAB_TOOL_MODE
} from "./workbench/constants.js";
import { useStepSessionRecord } from "./workbench/useStepSessionRecord.js";
import {
  buildViewerMeshAlert,
  buildViewerEditAlert
} from "./workbench/viewerAlerts.js";
import {
  buildNormalizedReferenceState,
  buildReferenceCacheKey,
  copyTextLines,
  computeNextSelectionIds,
  orderedStringListEqual,
  parseAssemblyPartReferenceSelectionId,
  topologyCompositionKeyMatches,
  uniqueStringList
} from "./workbench/referenceSelection.js";
import {
  entryAssetHash,
  entryHasMesh,
  entryHasReferences,
  entryMeshAssetSignature
} from "@hardcore/core/lib/entryAssets.js";
import {
  hasMeshGeometry,
  hasStepGlbByteCost,
  isLargeMeshData,
  isLargeStepGlbEntry
} from "@hardcore/core/lib/render/meshCost.js";
import { createAnimationClock, AnimationClockProvider, useAnimationClockStore } from "./workbench/animationClockStore.js";
import { measureFilterSnaps } from "./workbench/measureRulerState.js";
import { useStepMeasure } from "./workbench/useStepMeasure.js";
import { cadFileParamForEntry, fileKey } from "./workbench/entryPaths.js";
import {
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
  shouldRetainCompleteSameFileMesh
} from "./components/workbench/hooks/packageProgressiveLoad.js";
import { meshLoadErrorForViewer, shouldStartMeshLoad } from "./components/workbench/hooks/meshLoadTarget.js";
import { useViewerHost, usePromptDestination } from "../../host/context.js";
import { useWorkspaceDocument } from "../workspace/useWorkspaceDocument.js";
import { createCadPromptContext } from "./file-view/promptContext.js";
import { modelMenuDescriptor, partMenuDescriptor, topologyMenuDescriptor } from "./file-view/stepMenus.js";
import { nodeCopyText, selectionCopyPayload } from "./file-view/stepCopy.js";
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
    const translation = displayRecordExplodedViewTranslation(THREE, record);
    if (translation.lengthSq() > 1e-12) translationByRecord.set(record, translation);
  }
  return displayRecordsBounds(runtime.displayRecords, { partIds: new Set(normalizedPartIds), translationByRecord });
}

import {
  DEFAULT_LARGE_FILE_STATE,
  EMPTY_LIST,
  entryWithoutRenderAssets,
  normalizeLargeFileState
} from "./file-view/fileViewState.js";
import {
  addReferenceLookupKeys,
  buildStepTreeCopyReferenceMap,
  collectStepTreeRevealExpansionIds,
  collectStepTreeSubtreeIds,
  collectStepTreeTopologyLoadableNodeIds,
  expandedVisibleStepTreeTopologyNodeIds,
  referencesForExpandedStepTree,
  stepTreeTopologyOwnersForSelectors,
  copyableStepTreeNodeForWorkspace,
  findStepTreeTopologyNodeIdForReference
} from "./file-view/stepTreeSelection.js";

/**
 * State whose current value event handlers read synchronously (a pick, then a menu built from
 * it, in one gesture): every write goes through one setter that updates the ref and the state
 * together, so the two can never disagree and nothing re-syncs them after a render.
 */
function useSyncedState(initial) {
  const [value, setValue] = useState(initial);
  const ref = useRef(value);
  const set = useCallback((next) => {
    const resolved = typeof next === "function" ? next(ref.current) : next;
    ref.current = resolved;
    setValue(resolved);
  }, []);
  return [value, set, ref];
}

// The shared renderer consumes one prepared entry. FileViewer owns navigation,
// panel placement and persistence; the connection owns catalog subscriptions.
export default function StepSurface({ view, data }) {
  const clock = useMemo(() => createAnimationClock(), []);
  return <AnimationClockProvider value={clock}><StepSurfaceBody view={view} data={data} /></AnimationClockProvider>;
}


// `view` is the host's view props exactly as every shell renderer takes them, and `data` the
// prepared document: the workspace half of it (the prompt resource, the host's command and
// preference stores, the shell's services) is `useWorkspaceDocument`'s, as it is for every
// renderer on the shell.
function StepSurfaceBody({ view, data }) {
  const { client, entry, serverInfo, renderSession: cadRenderSession } = data;
  const slots = data.services.slots;
  const workspace = useWorkspaceDocument({ view, data });
  const { resource: documentResource, services, acknowledgeCommand } = workspace;
  const selectReference = workspace.commands.selectReference;
  const state = view.state;
  const colorScheme = view.appearance?.colorScheme;
  const host = useViewerHost();
  const destination = usePromptDestination();
  const promptAvailable = destination.available;
  const composerDestination = destination.kind === "composer";
  const { getAnimationClock } = useAnimationClockStore();
  const resolvedColorSchemeMode = colorScheme === "dark" ? "dark" : "light";
  const storeSnapshot = useSyncExternalStore(client.subscribe, client.getSnapshot, client.getSnapshot);
  const selectedKey = fileKey(entry);
  const liveEntry = workspace.entry;
  const manifestRevision = storeSnapshot.revision;
  const explicitFileParam = cadFileParamForEntry(entry);
  const catalogHydrated = storeSnapshot.hydrated;
  const catalogError = storeSnapshot.error || "";
  const selectedCatalogPending = liveEntry?.catalogPending === true;
  const [selectedReferenceIds, setSelectedReferenceIds, selectedReferenceIdsRef] = useSyncedState([]);
  const [largeFileState, setLargeFileState] = useState(() => normalizeLargeFileState(DEFAULT_LARGE_FILE_STATE));
  const [hoveredModelReferenceId, setHoveredModelReferenceId] = useState("");
  const [selectionFilter, setSelectionFilter] = useState("all");
  const [inspectionHighlight, setInspectionHighlight] = useState(null);
  const handleInspectionHighlight = useCallback((selection, label, context) => {
    setInspectionHighlight(selection ? { ...selection, label, context } : null);
  }, []);
  const [selectedPartIds, setSelectedPartIds, selectedPartIdsRef] = useSyncedState([]);
  const [selectedRenderPartIdByAssemblyPartId, setSelectedRenderPartIdByAssemblyPartId] = useState({});
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
  // Fullscreen, held here because the gates below run before the shell hook; the shell writes it.
  const presentation = usePresentationState();
  const presenting = presentation.presenting;
  const resolvedScene = useMemo(() => presenting ? { ...viewUpdate.scene, display: presentationDisplaySettings(viewUpdate.scene.display) } : viewUpdate.scene, [viewUpdate.scene, presenting]);
  const [hoveredListPartId, setHoveredListPartId] = useState("");
  const [hoveredModelPartId, setHoveredModelPartId] = useState("");
  const [stepUpdateInProgress, setStepUpdateInProgress] = useState(false);
  // The viewport's own alert, kept HERE: this renderer folds it into an alert of its own
  // (`viewerAlert` below) and hands the shell the composed result.
  const [viewerRuntimeAlert, setViewerRuntimeAlert] = useState(null);
  const rendering = resolvedScene.render.enabled;
  const resolvedThemeSettings = resolvedScene.theme;
  const resolvedMaterialOverrides = resolvedScene.materialOverrides || EMPTY_MATERIAL_OVERRIDES;
  const [tabToolMode, setTabToolMode] = useState(() => CAD_TOOL_MODES.restore(readShellState(state).tool));

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
    cancelReferenceLoad,
    loadMeshForEntry,
    loadReferencesForEntry,
    fatalLoadFailure
  } = useCadAssets({
    initialEntry: liveEntry,
    client,
    tessellationCache: cadRenderSession.tessellationCache,
    entryHasMesh,
    entryHasReferences,
    buildNormalizedReferenceState,
  });

  // File state uses the host's absolute identity; server requests use the
  // catalog's path relative to this client's served root.
  const editingFile = liveEntry ? cadFileParamForEntry(liveEntry) : explicitFileParam;
  const editingAvailable = /\.st(?:ep|p)$/i.test(editingFile || "");
  const editingPreview = useEditingPreview(editingFile, { client,
    enabled: editingAvailable && !selectedCatalogPending,
    catalogEntry: liveEntry,
  });
  // Unified render-artifact status for the selected entry: ready (render) | generating (loading) |
  // error (fatal). A missing/stale cache is not an issue — it just triggers a (re)build. Replaces
  // the per-entry step-source-status fetch, the mesh-stripping merge, and the build effect.
  const selectedArtifact = useArtifact(
    liveEntry ? cadFileParamForEntry(liveEntry) : "",
    {
      enabled: !selectedCatalogPending,
      freshnessKey: `${liveEntry?.hash || ""}:${manifestRevision}`,
      client,
    }
  );
  const editingHasView = Boolean(editingPreview.entry || entryHasMesh(liveEntry));
  const selectedArtifactGenerating = selectedArtifact.status === "compiling" && !editingHasView;
  // The in-flight build's own report of where it is (null until it reports, and for
  // every loading state that is not an artifact build). Only meaningful while
  // generating — a stale frame must not outlive the build that produced it.
  const selectedArtifactProgress = selectedArtifactGenerating ? selectedArtifact.progress : null;
  const activeStepArtifactGenerationFiles = useMemo(
    () => (selectedArtifactGenerating && liveEntry ? [fileKey(liveEntry)] : []),
    [selectedArtifactGenerating, liveEntry]
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
      const base = editingPreview.entry || (!liveEntry || selectedArtifact.status === "compiled" ||
        entryHasMesh(liveEntry)
        ? liveEntry
        : entryWithoutRenderAssets(liveEntry));
      if (!base) {
        return base;
      }
      const fileRefPrefix = fileRefPrefixByPath.get(cadFileParamForEntry(base)) || "";
      return fileRefPrefix ? { ...base, fileRefPrefix } : base;
    },
    [liveEntry, selectedArtifact.status, fileRefPrefixByPath, editingPreview.entry]
  );
  const previousPreviewTree = useRef(null);
  useEffect(() => {
    const previous = previousPreviewTree.current;
    const next = { file: selectedEntry?.file, hash: selectedEntry?.hash, preview: selectedEntry?.editingPreview };
    if (previewGeometryChanged(previous, next)) {
      setSelectedReferenceIds([]);
      setSelectedPartIds([]);
      setSelectedRenderPartIdByAssemblyPartId({});
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
          stepPath: liveEntry ? fileKey(liveEntry) : "",
        },
      }
    : null;
  // This renderer is only ever handed a STEP (its `matches`, index.ts), keyed per file, and an
  // entry is always present: so every capability a STEP has (parts, topology, Measure, a
  // sidecar's parameters, the Select and Draw tools) is simply on here, and nothing below asks
  // the format again.
  // The URL's path IS the directory, so there is nothing to select and no state to
  // reconcile — the Viewer always has exactly one directory, the one it was opened at.
  const stepArtifactGenerationAvailable = serverInfo
    ? serverInfo.stepArtifactGenerationAvailable !== false
    : true;
  // What this file's view opts into: a B-rep model takes every Display section, preset and
  // surface style. The shell configures the store with it (`features`).
  const viewFeatures = ALL_VIEW_FEATURES;
  const isAssemblyView = selectedEntry?.kind === "assembly";
  // Where this entry's motion comes from; the motion itself is `useStepMotion`'s, below.
  const {
    moduleUrl: selectedStepModuleUrl, sourceAnimation: selectedSourceAnimation, animationKey: selectedAnimationSourceKey
  } = stepMotionSources(selectedEntry);
  const selectedEntryHasMesh = entryHasMesh(selectedEntry);
  const selectedEntryHasReferences = entryHasReferences(selectedEntry);
  // The selected entry's render artifact is (re)building -> show the loading state. Replaces the
  // old !entryHasMesh + buildable-code derivation.
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
  const selectedMeshPartial = selectedMeshMatches && !meshStateIsComplete(meshState);

  // ---- motion: the kinematics module and Position, the routines and playback -------------------
  const motion = useStepMotion({
    entry: selectedEntry, fileKey: selectedKey, resources: client.resources,
    meshData: selectedMeshData, meshPartial: selectedMeshPartial,
    readStored: () => session.readStored(), clipboard: host.clipboard,
    reportError: (message) => shellRef.current?.reportActionError(message)
  });
  const {
    definition: selectedStepModuleDefinition, loading: selectedStepModuleLoading,
    topologyRequired: selectedStepModuleTopologyRequired, parameterValues: stepModuleParameterValues,
    animationState, animationRuntime: selectedAnimationRuntime, animationError: selectedAnimationError
  } = motion;

  const assemblyRoot = selectedAssemblyStructureReady
    ? selectedMeshData?.assemblyRoot || null
    : null;
  // An assembly tree already contains its occurrence metadata. Display-only
  // tessellation changes must not invalidate tree consumers through meshData.
  const stepPartMeshData = assemblyRoot ? null : selectedMeshData;
  const stepTreeRoot = useMemo(() => buildStepTreeRoot({
    selectedEntry,
    assemblyRoot,
    meshData: stepPartMeshData
  }), [assemblyRoot, selectedEntry, stepPartMeshData]);
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
    isAssemblyView && selectedEntryHasReferences
      ? collectStepTreeTopologyLoadableNodeIds(stepTreeRoot)
      : []
  ), [
    isAssemblyView,
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
    if (!isAssemblyView || !selectedEntryHasReferences) {
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
    : selectedMeshMatches && !!selectedMeshData;
  const supportsPartSelection = assemblyPartsLoaded && stepLeafParts.length > 0;
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
  // A fatal render-artifact error (not building) stops the loading spinner so the error surfaces.
  const artifactBlocksRender = selectedArtifact.status === "failed" && !editingHasView;
  const viewerLoading =
    (selectedArtifactGenerating || !artifactBlocksRender) &&
    status !== ASSET_STATUS.ERROR &&
    ((!selectedMeshMatches && !retainedPreviousStepMeshError) ||
      status === ASSET_STATUS.LOADING || selectedStepModuleLoading);
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
  // The shell's presentation report, held here because the edit alert below reads it before the shell hook runs.
  const presentationReport = usePresentationReport();
  const presentationPending = Boolean(selectedMeshData) &&
    presentationIsPending(presentationReport.state, { modelKey: selectedKey, key: presentationKey, renderMode: rendering });
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
  const drawModeActive = tabToolMode === TAB_TOOL_MODE.DRAW;

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
  // Declared here, above the LOD scheduler that is handed it: it reads only refs, so it is
  // safe this early, and a `const` read before its declaration is a TDZ crash, not undefined.
  const sampleViewportLodCamera = useCallback((options) => {
    const runtime = runtimeRefRef.current?.current;
    if (!runtimeModelKeyMatches(runtime, selectedKey)) return null;
    return sampleLodCamera(THREE, runtime, { ...options, selectedPartIds: lodSelectedPartIdsRef.current });
  }, [selectedKey]);
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
  const handleViewerAlertChange = useCallback((nextAlert) => {
    setViewerRuntimeAlert(nextAlert || null);
  }, []);


  const resetSelectionForStepUpdate = useCallback(() => {
    setSelectedPartIds([]);
    setSelectedReferenceIds([]);
    setSelectedRenderPartIdByAssemblyPartId({});
    setHoveredModelReferenceId("");
    setHoveredListPartId("");
    setHoveredModelPartId("");
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
        fileSheetKind: "step",
        stepSourceStatus: selectedStepSourceStatus,
        viewerAlert,
        warningAlert: annotationAlert,
        stepArtifactGenerationAvailable,
        activeGenerationFiles: activeStepArtifactGenerationFiles,
        serverInfo,
        artifactAdvisory: selectedArtifact.advisory
      })
  ), [
    activeStepArtifactGenerationFiles,
    selectedEntry,
    selectedArtifact.advisory,
    selectedArtifactGenerating,
    stepArtifactGenerationAvailable,
    selectedStepSourceStatus,
    viewerAlert,
    annotationAlert,
    serverInfo
  ]);


  // ---- this STEP's own slice of the per-file record --------------------------------------
  // The record is written soon after anything in it changes. A clip that is PLAYING writes
  // nothing: the clock moves every frame, and the stored time would be rewritten with it.
  const motionStateRef = motion.animationStateRef;
  const scheduleRecordSave = useCallback(() => { if (!motionStateRef.current.playing) shellRef.current?.scheduleStateSave(); }, [motionStateRef]);
  const session = useStepSessionRecord({
    state: view.state, entry: selectedEntry,
    tree: { selectedReferenceIds, selectedPartIds, expandedStepTreeNodeIds, hiddenPartIds },
    parameterValues: stepModuleParameterValues, animationState, clockTime: getAnimationClock, largeFileState,
    scheduleSave: scheduleRecordSave,
    // Everything this file was left with, once, before the first paint.
    restore(restored) {
      setSelectedReferenceIds(restored.tree.selectedReferenceIds);
      setSelectedPartIds(restored.tree.selectedPartIds);
      setExpandedStepTreeNodeIds(restored.tree.expandedStepTreeNodeIds);
      setHiddenPartIds(restored.tree.hiddenPartIds);
      setLargeFileState(normalizeLargeFileState(restored.largeFile));
      motion.restore(restored);
    }
  });

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

  useEffect(() => {
    setSelectionFilter("all");
    setInspectionHighlight(null);
  }, [selectedKey, artifactRevision]);
  const selectedStepParameterRuntime = useMemo(() => {
    if (
      !selectedStepModuleDefinition ||
      (selectedStepModuleTopologyRequired && !selectedSelectorRuntime)
    ) {
      return null;
    }
    return {
      definition: selectedStepModuleDefinition,
      parameterValues: normalizeStepModuleParameterValues(selectedStepModuleDefinition, stepModuleParameterValues),
      selectorRuntime: selectedSelectorRuntime,
      cadPath: selectedStepModuleDefinition.cadPath || stepMotionSources(selectedEntry).cadPath,
      sourceUrl: selectedStepModuleUrl
    };
  }, [
    selectedEntry,
    selectedSelectorRuntime,
    selectedStepModuleDefinition,
    selectedStepModuleTopologyRequired,
    selectedStepModuleUrl,
    stepModuleParameterValues
  ]);
  const selectedStepPartRootActive = !isAssemblyView && expandedStepTreeNodeIds.includes(STEP_MODEL_ROOT_ID);
  const plainStepReferencePickingEnabled = selectedEntryHasReferences && !isAssemblyView;
  const plainStepReferencePickingRequested =
    plainStepReferencePickingEnabled &&
    (selectedStepPartRootActive || selectedStepModuleTopologyRequired);
  const assemblyStepTreeTopologyLoadingEnabled =
    selectedEntryHasReferences &&
    isAssemblyView &&
    requestedStepTreeTopologyNodeIds.length > 0;
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
  const referenceLoadingExplicitlyRequested = selectedStepPartRootActive || selectedStepModuleTopologyRequired;
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

  const {
    currentReferences,
    activeReferenceMap,
    selectedReferences,
    selectedParts,
    hoveredReferenceId,
    hoveredPartId
  } = useCadWorkspaceSelectors({
    selectedReferencesMatch,
    referenceState,
    supportsPartSelection,
    assemblyParts,
    assemblyPartMap,
    selectedReferenceIds,
    selectedPartIds,
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
    setHoveredModelReferenceId,
    assemblyParts,
    validAssemblyPartIds: validAssemblySelectionIds,
    validHiddenPartIds: validAssemblyLeafIds,
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
  const isViewerTopologyReference = useCallback((reference) => (
    isFaceReference(reference) || isEdgeReference(reference)
  ), [isEdgeReference, isFaceReference]);
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
    if (!isAssemblyView || !selectedReferencesMatch) {
      return [];
    }
    return assignStepTreeTopologyReferencePartIds(stepTreeRoot, currentReferences);
  }, [
    currentReferences,
    isAssemblyView,
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
    return currentReferences;
  }, [
    currentReferences,
    focusedAssemblyPartReferences,
    focusedAssemblyTopologyActive,
    isAssemblyView
  ]);
  const stepTreeTopologyReferences = useMemo(() => {
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
  // Collapsing a part (including isolation exit) removes its exact topology.
  // Drop those selections too, rather than leaving invisible IDs in Copy/shortcuts.
  useEffect(() => {
    if (viewerLoading || stepInteractionBlocked || !stepTreeRoot || !selectedReferenceIds.length) return;
    const expandedOwners = new Set(expandedStepTreeTopologyNodeIds);
    const next = selectedReferenceIds.filter(id => {
      const partId = parseAssemblyPartReferenceSelectionId(id)?.partId;
      const owners = partId ? [isAssemblyView ? partId : STEP_MODEL_ROOT_ID]
        : stepTreeTopologyOwnersForSelectors(stepTreeRoot, [id], { isAssemblyView });
      return owners.every(owner => expandedOwners.has(owner));
    });
    if (next.length === selectedReferenceIds.length) return;
    setSelectedReferenceIds(next);
  }, [viewerLoading, stepInteractionBlocked, stepTreeRoot, selectedReferenceIds,
    expandedStepTreeTopologyNodeIds, isAssemblyView]);

  const viewerPickableFaces = useMemo(
    () => viewerPickableReferences.filter((reference) => isFaceReference(reference)),
    [isFaceReference, viewerPickableReferences]
  );
  const viewerPickableEdges = useMemo(
    () => viewerPickableReferences.filter((reference) => isEdgeReference(reference)),
    [isEdgeReference, viewerPickableReferences]
  );
  const hasViewerPickableTopology = Boolean(viewerPickableFaces.length || viewerPickableEdges.length);
  // Measuring needs a mesh to hit. Topology, when loaded, upgrades STEP hits
  // from free points to edge and face snaps.
  const measureModeActive = tabToolMode === TAB_TOOL_MODE.MEASURE &&
    Boolean(selectedMeshData) &&
    !stepInteractionBlocked &&
    !viewerLoading;
  const measure = useStepMeasure({ fileKey: selectedKey, revision: selectedEntry?.hash, picking: measureModeActive });
  useEffect(() => { if (measureModeActive) setInspectionHighlight(null); }, [measureModeActive]);
  const measureMeasurements = measure.measurements;

  const filteredViewerReferences = useMemo(() => filterSelectionReferences(viewerPickableReferences, selectionFilter),
    [viewerPickableReferences, selectionFilter]);
  const filteredViewerFaces = useMemo(() => filteredViewerReferences.filter(isFaceReference), [filteredViewerReferences, isFaceReference]);
  const filteredViewerEdges = useMemo(() => filteredViewerReferences.filter(isEdgeReference), [filteredViewerReferences, isEdgeReference]);
  // What the tool in hand may pick: Measure snaps to what its own filter says, Select to what
  // the selection filter allows.
  const measureSnaps = measureFilterSnaps(measure.filter);
  const viewerPickableFacesForTool = measureModeActive
    ? (measureSnaps.faces ? viewerPickableFaces : EMPTY_LIST) : filteredViewerFaces;
  const viewerPickableEdgesForTool = measureModeActive
    ? (measureSnaps.edges ? viewerPickableEdges : EMPTY_LIST) : filteredViewerEdges;
  const measureToolDisabled = viewerLoading || !selectedMeshData;
  const topologySelectionActive =
    (isAssemblyView && requestedStepTreeTopologyNodeIds.length > 0) ||
    topLevelReferenceSelectionActive;
  const referenceSelectionUnavailable = (
    selectedEntryHasReferences &&
    topologySelectionActive &&
    !viewerInAssemblyMode &&
    !selectedTopologyDeferredByCost &&
    (
      referenceStatus === REFERENCE_STATUS.DISABLED ||
      referenceStatus === REFERENCE_STATUS.ERROR ||
      (
        referenceStatus === REFERENCE_STATUS.READY &&
        !!effectiveSelectorRuntime &&
        !hasViewerPickableTopology
      )
    )
  );
  const referenceSelectionPending = (
    selectedEntryHasReferences &&
    topologySelectionActive &&
    !viewerInAssemblyMode &&
    !selectedTopologyDeferredByCost &&
    !referenceSelectionUnavailable &&
    !retainedPreviousStepMeshError &&
    (
      stepInteractionBlocked ||
      referenceStatus === REFERENCE_STATUS.IDLE ||
      referenceStatus === REFERENCE_STATUS.LOADING ||
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
  const viewportAnimation = motion.animationControls;
  // Animate is one mode with two ways in: the tool, and fullscreen, which is that
  // tool with the rest of the viewer put away (or no tool, without animation).
  const animationAvailable = animationControlsHaveContent(viewportAnimation);
  const animateToolActive = !presenting && animationAvailable && tabToolMode === TAB_TOOL_MODE.ANIMATE;
  const animateModeActive = animationAvailable && (presenting || animateToolActive);
  // A routine owns the model's pose only inside the mode. Outside it the clip is
  // released — stopped, rewound, the pose back with Position — so selection,
  // topology and Position never meet an animated model and need no special case
  // for one. Nothing of the playback survives: coming back starts from the start,
  // and a restored session that was mid-routine is released the same way.
  const releaseAnimation = motion.releaseAnimation;
  const animationOwnsPose = animationAvailable && viewportAnimation?.enabled !== false;

  // Pose: drag the joints by their handles. Present only where something can be
  // driven (a STEP's mate DOFs). The handles are rebuilt from the pose on screen,
  // so sliders, presets, Reset and a handle up the chain all carry them along.
  const stepPoseDefinition = selectedStepParameterRuntime?.definition || null;
  const poseAvailable = stepPosableDofs(stepPoseDefinition).length > 0;
  const poseToolActive = !presenting && poseAvailable && tabToolMode === TAB_TOOL_MODE.POSE;

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
    presentation,
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
    rendererState: session.write,
    toolRestore: CAD_TOOL_RESTORE,
    onCameraSettled: () => onLodCameraMoved(),
    preserveInteractionPixelRatio: viewPolicy.wireframeMode || viewPolicy.edgesVisible,
    runtimeLifecycle: stepRuntimeLifecycle,
    onRuntimeAlert: handleViewerAlertChange,
    presentationReport
  });
  shellRef.current = shell;
  const reportActionError = shell.reportActionError;
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
  const hoveredWholeTopologyReferencePartIds = useMemo(
    () => uniqueStringList(renderPartIdsForWholeTopologyReference(hoveredModelReferenceId)),
    [hoveredModelReferenceId, renderPartIdsForWholeTopologyReference]
  );
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

  // What the references resolve through when they are copied (`file-view/stepCopy.js`).
  const copyContext = useMemo(() => ({
    entry: selectedEntry, isAssemblyView, copyReferenceMap: stepTreeCopyReferenceMap, referenceMap: effectiveActiveReferenceMap,
    assemblyPartMap, displayRoot: displayStepTreeRoot, root: stepTreeRoot
  }), [assemblyPartMap, displayStepTreeRoot, effectiveActiveReferenceMap, isAssemblyView, selectedEntry, stepTreeCopyReferenceMap, stepTreeRoot]);
  const copySelectionPayload = useMemo(
    () => selectionCopyPayload(copyContext, { referenceIds: selectedReferenceIds, partIds: selectedPartIds }),
    [copyContext, selectedPartIds, selectedReferenceIds]
  );
  // Every copied line funnels through `copyTextLines`, here and in every other copy path below, so
  // the file prefix is applied at one point rather than threaded through each builder.
  const fileRefPrefix = selectedEntry?.fileRefPrefix || "";
  const canonicalCopySelectionLines = useMemo(
    () => copyTextLines(copySelectionPayload.lines, fileRefPrefix),
    [copySelectionPayload.lines, fileRefPrefix]
  );
  const copyButtonLabel = (copySelectionPayload.copiedCount || canonicalCopySelectionLines.length) > 1 ? "Copy References" : "Copy Reference";
  const copySelectedReferences = useCallback(async () => {
    const text = inspectionHighlight ? stepGeometryPromptText(inspectionHighlight, {
      referenceMap: effectiveActiveReferenceMap, parts: selectedMeshData?.parts || EMPTY_LIST, entry: selectedEntry,
    }) : canonicalCopySelectionLines.join("\n");
    if (!text || stepInteractionBlocked) return;
    try { await host.clipboard.writeText(text); }
    catch (error) { shellRef.current?.reportActionError(error instanceof Error ? error.message : "Could not copy reference"); }
  }, [canonicalCopySelectionLines, copySelectionPayload.copiedCount, stepInteractionBlocked, host.clipboard, inspectionHighlight, effectiveActiveReferenceMap, selectedMeshData, selectedEntry]);
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
    if (!normalizedNodeId) {
      return;
    }
    setActiveTreeNodeScrollKey(source === "viewer" || source === "reference" ? `${source}:${Date.now()}:${normalizedNodeId}` : "");
    // Selection reveals its details only in an already-open sidebar.
    shellRef.current?.revealFileSection("features", { open: false });
    if (expandAncestors || expandSelf || source === "reference") {
      expandStepTreeAroundNode(normalizedNodeId, { expandSelf });
    }
  }, [
    expandStepTreeAroundNode
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
    if (!multiSelect && selectedPartIdsRef.current.length) {
      setSelectedPartIds([]);
      setSelectedRenderPartIdByAssemblyPartId({});
    }
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
    setSelectedReferenceIds([]);
  }, []);

  // Copy is clipboard-only. Adding context is an explicit host action.
  const deliverReferenceText = useCallback((text) => host.clipboard.writeText(text), [host.clipboard]);
  const deliverPrompt = shell.deliverPrompt;
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
  }, [selectedKey, artifactRevision, selectionFilter, topologyTarget, loadFilterTopology]);
  const selectReferenceGroup = useCallback((referenceIds, { multiSelect = false } = {}) => {
    if (stepUpdateInProgress || !referenceIds.length || !referenceIds.every(id => ["face", "edge"].includes(effectiveActiveReferenceMap.get(id)?.selectorType))) return;
    const next = toggleReferenceGroupSelection(selectedReferenceIdsRef.current, referenceIds, multiSelect);
    ensureSelectTool();
    setSelectedPartIds([]);
    setSelectedRenderPartIdByAssemblyPartId({});
    setSelectedReferenceIds(next);
    setActiveTreeNodeScrollKey("");
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
    if (!multiSelect && selectedReferenceIdsRef.current.length) {
      setSelectedReferenceIds([]);
    }
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
    setInspectionHighlight(null);
    setSelectedPartIds([]);
    setSelectedRenderPartIdByAssemblyPartId({});
    setSelectedReferenceIds([]);
    setHoveredListPartId("");
    setHoveredModelPartId("");
    setHoveredModelReferenceId("");
    setViewerContextMenu(null);
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
      setSelectedReferenceIds(nextSelectedReferenceIds);
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
    togglePartSelection(STEP_MODEL_ROOT_ID, { multiSelect, renderPartId: nextReferenceId });
  }, [
    clearAssemblySelection,
    viewerPickableReferences,
    revealStepTreeNode,
    referencePartId,
    selectionFilter,
    tangentFaces,
    edgeChains,
    selectReferenceGroup,
    isAssemblyView,
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

  const doubleCopyReference = useRef(null);
  const handleModelReferenceDoubleActivate = useCallback((referenceId, { multiSelect = false } = {}) => {
    if (stepInteractionBlocked) return;
    if (!referenceId) {
      handleExitIsolate();
      return;
    }
    const reference = effectiveActiveReferenceMap.get(referenceId);
    const topology = reference && isViewerTopologyReference(reference);
    if (topology && selectionFilter !== "parts") {
      // A double-click copies the face or edge AND leaves it selected. The two clicks it is made
      // of each toggle it (or, close enough together, cancel each other's activation), so it is
      // selected here if they left it otherwise — the way a single click would select it.
      if (!selectedReferenceIdsRef.current.includes(referenceId)) handleModelReferenceActivate(referenceId, { multiSelect });
      doubleCopyReference.current?.(referenceId);
      return;
    }
    if (isAssemblyView) {
      const partId = topology ? referencePartId(reference) : referenceId;
      focusStepTreeNode(resolvePickedAssemblyPartId(partId), { reveal: false });
    }
  }, [stepInteractionBlocked, effectiveActiveReferenceMap, selectionFilter, isAssemblyView, handleModelReferenceActivate,
    referencePartId, focusStepTreeNode, handleExitIsolate, resolvePickedAssemblyPartId]);

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

  // The three menus, as descriptors built from the surface as it stands (`file-view/stepMenus.js`):
  // the model as a whole (a press on empty space, over a loaded model), one node's part menu
  // (the viewport and a Features row alike), and topology (a pick's faces and edges, or a row's).
  const openGlobalViewerContextMenu = useCallback(({ clientX = 0, clientY = 0 } = {}) => {
    setViewerContextMenu(selectedMeshData ? {
      x: Number(clientX) || 0,
      y: Number(clientY) || 0,
      ...modelMenuDescriptor({
        root: displayStepTreeRoot, isAssemblyView, expandedIds: expandedStepTreeNodeIds,
        loadableIds: loadableStepTreeTopologyNodeIds, hiddenCount: hiddenPartIds.length,
        zoomSelectionAvailable: zoomSelectionRef.current.available
      })
    } : null);
  }, [
    displayStepTreeRoot,
    expandedStepTreeNodeIds,
    hiddenPartIds.length,
    isAssemblyView,
    loadableStepTreeTopologyNodeIds,
    selectedMeshData
  ]);

  const assemblyNodeMenu = useCallback((nodeId, renderPartId = "") => {
    const id = String(nodeId || "").trim();
    return partMenuDescriptor({
      nodeId: id, renderPartId,
      node: assemblyPartMap.get(id) || findAssemblyNode(assemblyRoot, id) || null,
      leafIds: id ? renderPartIdsForAssemblySelection(id, String(renderPartId || "").trim() || id) : EMPTY_LIST,
      hiddenPartIds, focusedNodeIds: focusedAssemblyNodeIds, selectedPartIds: selectedPartIdsRef.current,
      root: displayStepTreeRoot, isAssemblyView, expandedIds: expandedStepTreeNodeIds, loadableIds: loadableStepTreeTopologyNodeIds,
      copyReferenceMap: stepTreeCopyReferenceMap, entry: selectedEntry, zoomSelectionAvailable: zoomSelectionRef.current.available
    });
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

  const topologyReferenceMenu = useCallback((referenceIds, label = "") => topologyMenuDescriptor({
    referenceIds, label, selectedReferenceIds: selectedReferenceIdsRef.current, referenceMap: effectiveActiveReferenceMap,
    copyReferenceMap: stepTreeCopyReferenceMap, entry: selectedEntry, zoomSelectionAvailable: zoomSelectionRef.current.available
  }), [
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
      reportActionError(retainedPreviousStepMeshError
        ? "Selection unavailable because the STEP update failed."
        : "STEP update in progress. Please wait.");
      return;
    }
    const copyText = copyTextLines(menu?.copyText, fileRefPrefix).join("\n");
    if (!copyText) {
      reportActionError("No selector ref is available for this node");
      return;
    }
    try {
      await deliverReferenceText(copyText);
    } catch (error) {
      reportActionError(error instanceof Error ? error.message : "Failed to copy reference");
    }
  }, [deliverReferenceText, fileRefPrefix, retainedPreviousStepMeshError, stepInteractionBlocked]);

  const copyStepTreeContextMenuReference = useCallback(async (id, { topology = false, toPrompt = false } = {}) => {
    if (stepInteractionBlocked) {
      reportActionError(retainedPreviousStepMeshError
        ? "Selection unavailable because the STEP update failed."
        : "STEP update in progress. Please wait.");
      return;
    }
    const normalizedId = String(id || "").trim();
    if (!normalizedId) {
      reportActionError("No selector ref is available for this node");
      return;
    }
    const copyText = nodeCopyText(copyContext, normalizedId, { topology });
    if (!copyText) {
      reportActionError("No selector ref is available for this node");
      return;
    }
    try {
      if (toPrompt) addReferenceText(copyText);
      else {
        await deliverReferenceText(copyText);
      }
    } catch (error) {
      reportActionError(error instanceof Error ? error.message : "Failed to copy reference");
    }
  }, [
    deliverReferenceText,
    addReferenceText,
    copyContext,
    retainedPreviousStepMeshError,
    stepInteractionBlocked
  ]);

  doubleCopyReference.current = id => copyStepTreeContextMenuReference(id, {
    topology: Boolean(effectiveActiveReferenceMap.get(id) && isViewerTopologyReference(effectiveActiveReferenceMap.get(id)))
  });

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
      reportActionError("CAD Viewer camera not ready");
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
      reportActionError("No geometry to fit");
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
    const copyText = copyTextLines(menu?.copyText, fileRefPrefix).join("\n");
    if (!copyText) {
      reportActionError("No selector ref is available for this node");
      return;
    }
    addReferenceText(copyText);
  }, [addReferenceText, fileRefPrefix]);

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
    // Measure activation is idempotent; clearing retained results is an explicit toolbar action.
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
    if (!presenting && tabToolMode === TAB_TOOL_MODE.MEASURE) {
      // Escape cancels the measurement in progress and leaves the tool armed, the way it does
      // in a CAD measure tool. Only once there is nothing to cancel does it leave the tool.
      if (measure.drafting) measure.cancelDraft();
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
      setSelectedPartIds(parts);
      setSelectedReferenceIds(references);
      setInspectionHighlight(null);
      setSelectedRenderPartIdByAssemblyPartId(current => Object.fromEntries(parts.map(id => [id, renderPartIdForAssemblySelection(id, current[id])]).filter(([, id]) => id)));
      const last = selections[selections.length - 1];
      revealStepTreeNode(last.kind === 'part' ? last.id : findStepTreeTopologyNodeIdForReference(displayStepTreeRoot, last.id) || referencePartId(effectiveActiveReferenceMap.get(last.id)), { source: 'reference' });
    },
    clearSelection() {
      setSelectedPartIds([]);
      setSelectedRenderPartIdByAssemblyPartId({});
      clearReferenceSelection();
      setInspectionHighlight(null);
    }
  };

  const selectionToolActive = tabToolMode === TAB_TOOL_MODE.REFERENCES;
  const canAddInspectionContext = promptAvailable &&
    inspectionHighlight?.context?.file === selectedEntry?.file;
  let selectionCount = selectedReferences.length + selectedParts.length
    + (!isAssemblyView && selectedPartIds.includes(STEP_MODEL_ROOT_ID) ? 1 : 0);
  if (inspectionHighlight) {
    selectionCount = 0;
    if (inspectionHighlight.label && !viewerLoading && !stepUpdateInProgress) {
      if (canAddInspectionContext) selectionCount = inspectionHighlight.faceIds.length + inspectionHighlight.partIds.length;
      else if (promptAvailable) selectionCount = inspectionHighlight.faceIds.length + inspectionHighlight.partIds.length;
    }
  }
  // Every CAD format shares the View settings and camera contract.

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
      onParameterChange: motion.onParameterChange
    });
  }, [poseToolActive, stepPoseDefinition, selectedStepParameterRuntime, stepPoseFeatures, motion.onParameterChange]);

  // ---- the viewport ---------------------------------------------------------------------------
  // What the viewport is ALLOWED to show and pick just now: nothing of the model under Pose,
  // Animate or fullscreen; no topology while a previous mesh is held over an update.
  const topologySelectionDeferred = Boolean(selectedTopologyDeferredByCost && selectedMeshData);
  // Animate, like fullscreen, is watching, and Pose offers its knobs alone.
  const watching = presenting || animateToolActive || Boolean(jointHandles);
  const pickMode = watching || retainingPreviousStepMesh ? VIEWER_PICK_MODE.NONE : viewerPickModeForRenderPane({
    selectionFilter,
    topologySelectionPending: referenceSelectionPending,
    topologySelectionUnavailable: referenceSelectionUnavailable,
    topologySelectionDeferred,
    topologyPickingActive: Boolean(viewerPickableFacesForTool.length || viewerPickableEdgesForTool.length),
    viewerMode,
    assemblyPickingActive: viewerInAssemblyMode,
    focusedPartIds: focusedAssemblyRenderPartIds,
    measureMode: measureModeActive
  });
  // One shared empty list: a fresh [] per render — per animation frame — invalidated the
  // layers' pickable memos and reference map.
  const pickable = list => (!retainingPreviousStepMesh && !watching ? list : EMPTY_LIST);
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
    previewMode: presenting,
    pickMode,
    pickableParts: !retainingPreviousStepMesh ? viewerAssemblyRenderParts : EMPTY_LIST,
    hiddenPartIds: viewerHiddenPartIdsForRenderPane({ inspectionEnabled: true, hasParts: true, hiddenPartIds: hiddenPartIds }),
    selectedPartIds: presenting ? EMPTY_LIST : viewerSelectedPartIdsForRenderPane({ renderMode: resolvedScene.render.enabled, hasParts: true,
      selectedPartIds: inspectionHighlight ? inspectionHighlight.partIds || EMPTY_LIST : viewerSelectedPartIds }),
    hoveredPartId: !presenting ? viewerHoveredPartIds : "",
    hoveredReferenceId: !presenting && !retainingPreviousStepMesh ? effectiveHoveredReferenceId : "",
    selectedReferenceIds: !presenting && !retainingPreviousStepMesh
      ? (inspectionHighlight ? inspectionHighlight.faceIds || EMPTY_LIST : selectedReferenceIds) : EMPTY_LIST,
    selectorRuntime: viewerSelectorRuntimeForRenderPane({ renderMode: resolvedScene.render.enabled, hasTopology: true,
      retainingPreviousStepMesh: retainingPreviousStepMesh, selectorRuntime: effectiveSelectorRuntime }),
    stepParameterRuntime: selectedStepParameterRuntime,
    // {clip, elapsedSec, playing} or null. Null means no clip is selected, and the evaluator never runs.
    stepAnimationRuntime: selectedAnimationRuntime,
    animateMode: presenting || animateToolActive,
    jointHandles: presenting ? null : jointHandles,
    measureState: presenting ? null : inspectionHighlight?.measurement ? { measurements: [inspectionHighlight.measurement] } : measure.state,
    activeMeasurementId: inspectionHighlight?.measurement?.id || measure.activeId,
    measureModeActive: !presenting && measureModeActive,
    onLodCameraChange: onLodCameraMoved,
    onMeshSourceAdoption: handleDisplayMeshAdoption,
    onViewerAlertChange: handleViewerAlertChange,
    onHoverReferenceChange: !presenting ? handleModelHoverChange : null,
    onActivateReference: !presenting ? handleModelReferenceActivate : null,
    onDoubleActivateReference: !presenting ? handleModelReferenceDoubleActivate : null,
    onMeasurePick: !presenting ? measure.onPick : null,
    onMeasureHoverPoint: !presenting ? measure.onHoverPoint : null,
    pickAtRef
  };
  const viewPolicyResolved = useStepViewPolicy({
    meshData: selectedDisplayMeshData, themeSettings: resolvedThemeSettings, displaySettings: resolvedScene.display,
    renderMode: resolvedScene.render.enabled, renderConfiguration: resolvedScene.render.configuration,
    renderPartsIndividually: Boolean(selectedStepParameterRuntime) || Boolean(selectedAnimationRuntime) ||
      Boolean(Object.keys(selectedDisplayMeshData?.appearance?.materials || {}).length) ||
      Boolean(selectedStepParameterRuntime?.definition) || Boolean(selectedAnimationRuntime?.clip),
    pickMode, pickableParts: layerProps.pickableParts,
    pickableFaces: pickable(viewerPickableFacesForTool), pickableEdges: pickable(viewerPickableEdgesForTool),
    hiddenPartIds: layerProps.hiddenPartIds, selectedPartIds: layerProps.selectedPartIds,
    focusedPartId: focusedAssemblyRenderPartIds
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
  const removeMeasurements = () => {
    measure.clear();
    if (tabToolMode === TAB_TOOL_MODE.MEASURE) handleSelectTabToolMode(TAB_TOOL_MODE.REFERENCES);
  };
  const modelEffects = useModelTools({ modelKey: selectedEntry?.file, view: desiredScene.view,
    features: viewFeatures, store: viewSettingsStore, mesh: selectedDisplayMeshData,
    disabled: toolIdle, selectedTool: tabToolMode, onSelect: handleSelectTabToolMode, hidden: presenting,
    measure: {
      Icon: Ruler, unavailable: measureToolDisabled, isPicking: measureModeActive,
      hasMeasurements: measureMeasurements.length > 0,
      onRemove: removeMeasurements,
      controls: <MeasurePanel measurements={measureMeasurements} activeId={measure.activeId}
        onActivate={measure.setActiveId} onDelete={measure.onDelete} />
    } });
  const tools = [
    shell.tools.own({
      id: TAB_TOOL_MODE.REFERENCES,
      label: referenceSelectionPending ? "Preparing selection" : "Select",
      icon: <MousePointer2 className="size-3" strokeWidth={2} aria-hidden="true" />,
      active: !topologySelectionDeferred && selectionToolActive, disabled: selectDisabled,
      description: "Select again to choose a selection filter",
      secondPressOpensMenu: true,
      onSelect: () => handleSelectTabToolMode(TAB_TOOL_MODE.REFERENCES),
      menu: trigger => <SelectionFilterMenu value={selectionFilter} trigger={trigger}
        onChange={value => { setSelectionFilter(value); handleSelectTabToolMode(TAB_TOOL_MODE.REFERENCES); }} />,
      subToolbar: <ToolFilterNote options={SELECTION_FILTERS} value={selectionFilter}
        active={selectionToolActive} notice={topologyFilterHint} />
    }),
    { ...shell.tools.draw, disabled: toolIdle },
    shell.tools.own({ id: TAB_TOOL_MODE.MEASURE, label: "Measure",
      icon: <Ruler className="size-3" strokeWidth={2} aria-hidden="true" />,
      active: tabToolMode === TAB_TOOL_MODE.MEASURE || measureMeasurements.length > 0, disabled: measureToolDisabled,
      secondPressOpensMenu: true, menuOnCornerOnly: measureMeasurements.length > 0,
      onMenuSelect: () => handleSelectTabToolMode(TAB_TOOL_MODE.MEASURE),
      onSelect: () => measureMeasurements.length ? removeMeasurements() : handleSelectTabToolMode(TAB_TOOL_MODE.MEASURE),
      menu: trigger => <SelectionFilterMenu trigger={trigger} value={measure.filter}
        options={MEASURE_SELECTION_FILTERS} menuLabel="Measure snapping" hint="" onChange={value => {
          measure.setFilter(value); measure.cancelDraft();
          handleSelectTabToolMode(TAB_TOOL_MODE.MEASURE);
        }} /> }),
    ...modelEffects.tools,
    // Position follows the model effects; only files with movable joints offer it.
    poseAvailable ? shell.tools.own({ id: TAB_TOOL_MODE.POSE, label: "Position",
      icon: <Spline className="size-3" strokeWidth={2} aria-hidden="true" />,
      active: poseToolActive, disabled: toolIdle,
      onSelect: () => {
        if (!poseToolActive) handleSelectTabToolMode(TAB_TOOL_MODE.POSE);
        shell.revealFileSection("position");
      } }) : null,
    // The shared animation tool uses this action when routines exist.
    animationAvailable ? shell.tools.own({ id: TAB_TOOL_MODE.ANIMATE, label: "Animate",
      icon: <Play className="size-3" aria-hidden="true" />,
      active: animateToolActive, disabled: toolIdle,
      onSelect: () => { if (!animateToolActive) { handleSelectTabToolMode(TAB_TOOL_MODE.ANIMATE); if (!animationState.playing) motion.onPlayToggle(); } },
    }) : null,
  ].filter(Boolean);

  // ---- the bottom action ----------------------------------------------------------------------
  const selectionActionVisible = selectionCount > 0 && !stepUpdateInProgress && !referenceSelectionPending
    && !referenceSelectionUnavailable && !topologySelectionDeferred;
  const bottomAction = drawModeActive
    ? (stepUpdateInProgress || referenceSelectionPending || referenceSelectionUnavailable || topologySelectionDeferred ? null : undefined)
    : selectionActionVisible ? {
      label: copyButtonLabel,
      onInvoke: copySelectedReferences,
      children: slots?.selectionExtras && selectionCount > 0 && !viewerLoading && !stepInteractionBlocked ? <slots.selectionExtras
        selection={Object.freeze(createSelectionPromptContext().parts.filter(part => part.kind === 'reference').map(part => part.reference))}
        selectionKey={selectionKey}
        disabled={viewerLoading || stepInteractionBlocked || !promptAvailable}
        createContext={createSelectionPromptContext}
      /> : null
    } : null;

  // ---- the file's panel ------------------------------------------------------------------------
  const stepPanel = useStepPanel({
    positionRuntime: motion.positionControls,
    selectedMeshData: selectedDisplayMeshData,
    selectedSourceAppearance,
    client,
    geometryInspection: { file: selectedEntry?.file, revision: artifactRevision,
      references: !viewerLoading && !stepUpdateInProgress ? isAssemblyView ? assemblyStepTreeTopologyReferences : selectedSelectorRuntime?.references || EMPTY_LIST : EMPTY_LIST,
      parts: !viewerLoading && !stepUpdateInProgress ? selectedMeshData?.parts || EMPTY_LIST : EMPTY_LIST,
      onHighlight: handleInspectionHighlight, onLoadTopology: loadInspectionTopology },
    open: filePanelOpen && !presenting,
    selectedEntry,
    viewerLoading: viewerLoading || assemblySidebarLoading,
    isAssemblyView,
    stepTreeRoot: displayStepTreeRoot,
    expandedTreeNodeIds: expandedStepTreeNodeIds,
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
    onCopySelection: copySelectedReferences,
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
    statusItems: selectedFileStatusItems
  });

  return <RendererShell shell={shell} tools={tools} playback={viewportAnimation} toolPanels={modelEffects.panels} panel={stepPanel}
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

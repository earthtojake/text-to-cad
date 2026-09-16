"use client";

import { buildRobotComponentGeometry, robotComponents } from "@/workbench/robotComponents";
import { useRobotComponentSelection } from "@/workbench/useRobotComponentSelection";

import * as THREE from "three";
import { startTransition, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ArrowLeftRight, ArrowRight, Circle, Eraser, Minus, PaintBucket, PenTool, Square } from "lucide-react";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import CadRenderPane from "./workbench/CadRenderPane";
import { useViewportLod } from "../render/useViewportLod";
import { lodSceneMayMove } from "../render/lodCameraSample.js";
import { registerLodDisplaySource } from "../render/lodSceneAdoption.js";
import FileViewerSidebar from "./workbench/FileViewerSidebar";
import { buildDisplaySettingsTab } from "./workbench/DisplaySettingsTab";
import { buildRenderSettingsTab } from "./workbench/RenderSettingsTab";
import { buildMaterialsSettingsTab } from "./workbench/MaterialsSettingsTab";
import { prefetchRenderStudio } from "@/render/renderStudioChunk";
import MeshFileSheet from "./workbench/MeshFileSheet";
import { DXF_PREVIEW_REFERENCE_THICKNESS_MM } from "cadgen-js/lib/dxf/previewGlb";
import { dxfDataIsDocument } from "cadgen-js/lib/dxf/parseDxf";
import { loadRenderDxf } from "cadgen-js/lib/renderAssetClient";
import { extractOrderedDxfBendLines } from "cadgen-js/lib/dxf/buildPreviewMesh";
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
} from "./workbench/DxfSettingsSection";
import { buildDxfLayersTab } from "./workbench/DxfLayersSection";
import StepFileSheet from "./workbench/StepFileSheet";
import { poseValuesForPreset } from "./workbench/PoseControlsSection";
import StatusToast from "./workbench/StatusToast";
import UrdfFileSheet from "./workbench/UrdfFileSheet";
import ViewerAlertDialog from "./workbench/ViewerAlertDialog";
import ViewerLoadingOverlay from "./workbench/ViewerLoadingOverlay";
import {
  ARTIFACT_PROGRESS_POLL_MS
} from "@/workbench/artifactProgress.js";
import FloatingToolBar from "./workbench/FloatingToolBar";
import CadWorkspaceTopBar from "./workbench/CadWorkspaceTopBar";
import CadWorkspaceHome from "./workbench/CadWorkspaceHome";
import { useCadAssets } from "./workbench/hooks/useCadAssets";
import { useEditingPreview } from "./workbench/hooks/useEditingPreview.js";
import { useViewportQualityStatus } from "./workbench/hooks/useViewportQualityStatus.js";
import { previewGeometryChanged } from "@/workbench/editingPreview.js";
import { buildArtifactWarningAlert } from "@/workbench/artifactWarnings.js";
import { resolveFileStatus } from "@/workbench/fileStatus.js";
import { useViewerAutoReload } from "@/workbench/useViewerAutoReload.js";
import { viewerLoadingState } from "@/workbench/viewerLoading.js";
import {
  resolveDesktopPanelWidths,
  useCadWorkspaceLayout
} from "./workbench/hooks/useCadWorkspaceLayout";
import { useCadWorkspaceSelection } from "./workbench/hooks/useCadWorkspaceSelection";
import { useCadDirectorySession } from "./workbench/hooks/useCadDirectorySession";
import { useCadWorkspaceSelectors } from "./workbench/hooks/useCadWorkspaceSelectors";
import { useCadWorkspaceShortcuts } from "./workbench/hooks/useCadWorkspaceShortcuts";
import { useSourceMaterialSession } from "./workbench/hooks/useSourceMaterialSession.js";
import {
  applyColorSchemeToDocument,
  DARK_COLOR_SCHEME_ID,
  readColorSchemePreference,
  resolveColorSchemeMode,
  writeColorSchemePreference
} from "@/ui/colorScheme";
import { useSystemPrefersDark } from "@/ui/useSystemPrefersDark";
import { useChromeBackdropColor } from "@/ui/useChromeBackdropColor";
import { sceneBackdropEdgeColor } from "../workbench/chromeBackdrop.js";
import {
  displayModeForcesEdges,
  displayModeIsWireframe,
  normalizeDisplaySettings
} from "cadgen-js/lib/displaySettings";
import { RENDER_QUALITY, resolveSceneSettings } from "cadgen-js/common/sceneSettings.js";
import {
  annotatePerspectiveSnapshot,
  clonePerspectiveSnapshot
} from "cadgen-js/lib/perspective";
import {
  ASSET_STATUS,
  DOCUMENT_TITLE,
  DRAWING_TOOL,
  RENDER_FORMAT,
  REFERENCE_STATUS,
  TAB_TOOL_MODE
} from "@/workbench/constants";
import {
  FILE_SHEET_SECTION_IDS,
  defaultOpenFileSheetSectionIds,
  normalizeFileSheetOpenSectionIds,
  renderedFileSheetSectionIds,
  shouldOpenFileSheetForSelectionReveal
} from "@/workbench/fileSheetSections";
import { useEmbeddedGlbAnimation } from "@/workbench/useEmbeddedGlbAnimation";
import {
  entrySourceFormat,
  fileSheetKindForEntry,
  isRobotRenderFormat
} from "cadgen-js/lib/fileFormats";
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
} from "cadgen-js/lib/renderCapabilities";
import {
  buildViewerAnnotationAlert,
  buildViewerMeshAlert,
  buildViewerEditAlert,
  fileStatusAlertKey,
  resolveFileStatusAlert
} from "@/workbench/viewerAlerts";
import {
  buildParameterValuesCopyText,
  parseParameterValuesPasteText
} from "@/workbench/parameterControls";
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
  pendingReferenceActivationMatches,
  topologyCompositionKeyMatches,
  uniqueStringList
} from "@/workbench/referenceSelection";
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
} from "cadgen-js/lib/entryAssets";
import {
  hasStepGlbByteCost,
  isLargeMeshData,
  isLargeStepGlbEntry
} from "cadgen-js/lib/render/meshCost";
import {
  cadWorkspaceDefaultFileSheetWidthForViewport,
  cloneDrawingStrokes,
  cloneTabSnapshot,
  createTabRecord,
  drawingStrokesEqual,
  readCadDirectorySessionState,
  writeCadDirectorySessionState,
  tabSnapshotEqual,
  CAD_WORKSPACE_DEFAULT_SIDEBAR_WIDTH,
  CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH
} from "@/workbench/persistence";
import {
  createFileSessionSnapshot,
  normalizeFileSessionNamespace,
  pruneFileSessionState,
  readFileSessionState,
  writeFileSessionState
} from "@/workbench/fileSessionState";
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
} from "@/workbench/renderSessionState.js";
import {
  CAD_DIRECTORY_STORAGE_EVENT_ACTION,
  cadDirectoryStorageEventAction
} from "@/workbench/storageEvents";
import {
  shallowObjectValuesEqual,
  toFiniteNumber
} from "@/workbench/valueUtils";
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
} from "cadgen-js/common/animationClock";
import {
  getAnimationClock,
  resetAnimationClock,
  setAnimationClock
} from "@/workbench/animationClockStore";
import { resolveStepModuleLoad } from "@/workbench/stepModuleLoad";
import {
  applyMeasureRulerDelete,
  applyMeasureRulerHover,
  applyMeasureRulerPick,
  cancelMeasureRulerDraft,
  clearMeasureRulerMeasurements,
  measureRulerStateForChange
} from "@/workbench/measureRulerState";
import {
  buildUrdfJointAnglesCopyText,
  cloneJointValueMap,
  findBestMatchingJointValueState,
  interpolateTrajectoryJointValues,
  srdfHomeGroupStateJointValuesToDisplay,
  srdfGroupStateJointValuesToDisplay
} from "@/workbench/robotMotionControls";
import {
  CAD_WORKSPACE_LAYOUT_MODE,
  getCadWorkspaceLayoutMode,
  shouldCadWorkspaceDefaultFileSettingsOpen
} from "@/workbench/breakpoints";
import {
  buildSidebarDirectoryTree,
  cadFileParamForEntry,
  cadPathForEntry,
  collectAncestorDirectoryIds,
  collectSidebarDirectoryIds,
  findEntryByUrlPath,
  fileKey,
  missingFileRefForCatalog,
  readCadParam,
  selectedEntryKeyFromUrl,
  sidebarDirectoryIdForEntry,
  sidebarLabelForEntry,
  shouldDeferFileParamSelection,
  writeCadParam,
} from "@/workbench/sidebar";
import { buildCadRefToken, isNativeCadSelector } from "cadgen-js/lib/cadRefs.js";
import {
  stepModuleRequiresTopology,
  stepModuleTopologyOccurrenceIds
} from "@/workbench/topologyCapabilities";
import { shortestUniquePathSuffixes } from "cadgen-js/lib/filePathSuffix.js";
import {
  applyUrdfPoseToMeshData,
  buildDefaultUrdfJointValues,
  buildUrdfMeshGeometry,
  clampJointValueDeg,
  linkOriginInFrame,
  rootPointInFrame
} from "cadgen-js/lib/urdf/kinematics";
import {
  advanceUrdfJointValues,
  interpolateUrdfJointValues,
  jointValueMapsClose,
  URDF_JOINT_ANIMATION_DURATION_MS,
  URDF_JOINT_ANIMATION_EPSILON,
  URDF_JOINT_ANIMATION_FOLLOW_MS
} from "cadgen-js/lib/urdf/jointAnimation";
import { refreshCadCatalog, requestArtifactStatus } from "../workbench/cadManifestStore.js";
import { useArtifact } from "./workbench/hooks/useArtifact.js";
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
} from "cadgen-js/lib/assembly/meshData";
import {
  assemblyNodeContainsNode,
  minimalAssemblyIsolationNodeIds,
  selectedReferenceIdsOutsideFocusedAssemblyNodes,
  selectableViewerNodeIdsForExpandedTree
} from "@/workbench/assemblyIsolation";
import {
  assignStepTreeTopologyReferencePartIds,
  buildStepTreeRoot,
  buildStepTreeRootWithTopology,
  collectStepTreeAncestorIds,
  flattenVisibleStepTreeRows,
  STEP_MODEL_ROOT_ID,
  STEP_MODEL_RENDER_PART_ID,
  STEP_TREE_TOPOLOGY_NODE_PREFIX,
  stepTreeNodeChildren
} from "cadgen-js/lib/step/stepTree";
import {
  normalizeStepModuleParameterValues
} from "cadgen-js/common/stepModule";
import {
  meshStateIsComplete,
  shouldRetainCompleteSameFileMesh,
  tolerantAnimationClip
} from "./workbench/hooks/packageProgressiveLoad.js";
import { meshLoadErrorForViewer, shouldStartMeshLoad } from "./workbench/hooks/meshLoadTarget.js";
import {
  kinematicsModuleDefinitionFromSidecar,
  loadKinematicsModuleDefinition,
  previewKinematicsModuleDefinition
} from "cadgen-js/common/kinematicsModule";
import { validateSourceSidecar } from "cadgen-js/common/sourceSidecar.js";
import { loadSourceAnimation, validateAnimationClips } from "cadgen-js/common/renderModule";
import {
  normalizeParameterValue,
  normalizeParameterValues
} from "cadgen-js/common/parameters.js";
import { copyTextToClipboard, readTextFromClipboard } from "@/ui/clipboard";
import {
  applySourceMaterialOverlayToMeshData,
  sourceAppearanceHasMaterials,
  sourceMaterialGeometry
} from "@/workbench/sourceMaterialSession";
import {
  copyTargetsForFileAccessAsset,
  fileAccessAssetsForEntry,
  viewerDeepLinkForFileAccessAsset
} from "@/workbench/fileAccessAssets";

const DEFAULT_DOCUMENT_TITLE = "CAD Viewer";
// The source formats whose renderable geometry lives in a store render package, and
// therefore go through the /__cad/artifact state machine before they can render. Mirrors
// `owns_entry` in cadgen's viewer/artifact.py; an entry listed here and not there (or the
// reverse) is a format that either never builds or reports ready forever.
// Which formats build a package before they can render is a capability
// (`artifactManaged`), declared once and mirrored against the server's `owns_entry`.
// File-sheet kinds that render nothing but a status tab. A mesh never had file-specific
// controls; DXF lost its when the geometry moved into a baked render package, whose
// settings the producer owns.
const STATUS_ONLY_FILE_SHEET_KINDS = Object.freeze(["mesh", "dxf"]);

function statusOnlyFileSheetTitle(sourceFormat) {
  return renderFormatLabel(sourceFormat) || "STL";
}

// Single user-facing label for "the viewer is (re)generating the render artifacts a STEP model
// needs before it can render" — used for both the filename status chip and its tooltip across every
// artifact-generation trigger (first build, stale rebuild, source-changed regen). Browser-side
// asset-load/parse stages ("loading mesh", reference "loading topology", etc.) are a different
// concept and keep their own wording.
// The URDF loader reports its stage in lower case ("loading meshes 7/13") because the
// file-list chip reads that way; the viewport card is a sentence and needs a capital.


const EMPTY_LIST = Object.freeze([]);
const EMPTY_MATERIAL_OVERRIDES = Object.freeze({});
const URDF_POSE_PICKER_DEFAULT_CENTER = Object.freeze([0, 0, 0]);
const DESKTOP_SIDEBAR_MIN_WIDTH = 150;
const DESKTOP_SIDEBAR_MAX_WIDTH = 520;
const DEFAULT_SIDEBAR_WIDTH = CAD_WORKSPACE_DEFAULT_SIDEBAR_WIDTH;
const DESKTOP_TAB_TOOLS_MIN_WIDTH = 240;
const DESKTOP_TAB_TOOLS_MAX_WIDTH = 448;
const DEFAULT_TAB_TOOLS_WIDTH = CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH;

function sourceAnimationForEntry(entry) {
  return (entry?.editingPreview ? entry.previewAnimation : entry?.sourceSidecar?.animation) || null;
}

function sourceAnimationKeyForEntry(entry) {
  if (!sourceAnimationForEntry(entry)) return "";
  return `${fileKey(entry)}:${entry?.animationHash || entry?.documentHash || entry?.hash || "animation"}`;
}

const CAD_WORKSPACE_TOP_BAR_HEIGHT = 44;
const DEFAULT_LARGE_FILE_STATE = Object.freeze({
  selectableTopologyEnabled: false
});

function normalizeLargeFileState(value = {}) {
  return {
    selectableTopologyEnabled: value?.selectableTopologyEnabled === true
  };
}

function readViewerViewportWidth() {
  if (typeof window === "undefined") {
    return 1600;
  }
  const width = Number(window.innerWidth);
  return Number.isFinite(width) && width > 0 ? width : 1600;
}

function readViewerLayoutMode() {
  return getCadWorkspaceLayoutMode(readViewerViewportWidth());
}

function readDirectorySessionState(viewportWidth = readViewerViewportWidth()) {
  return readCadDirectorySessionState({
    defaultFileSheetWidthPx: cadWorkspaceDefaultFileSheetWidthForViewport(viewportWidth)
  });
}

function readInitialFileSheetOpen() {
  const storedOpen = readDirectorySessionState().fileSheetOpen;
  return typeof storedOpen === "boolean"
    ? storedOpen
    : shouldCadWorkspaceDefaultFileSettingsOpen(readViewerViewportWidth());
}

function readInitialFileSheetWidth() {
  const viewportWidth = readViewerViewportWidth();
  return (
    readDirectorySessionState(viewportWidth).fileSheetWidthPx ||
    cadWorkspaceDefaultFileSheetWidthForViewport(viewportWidth)
  );
}

function readInitialFileSheetWidthIsCustom() {
  const viewportWidth = readViewerViewportWidth();
  return readDirectorySessionState(viewportWidth).fileSheetWidthPx != null;
}

function stepTreeNodeIdForWorkspace(node) {
  return String(node?.id || node?.occurrenceId || "").trim();
}

function nativeCadSelectorCandidate(value) {
  const selector = String(value || "").trim();
  return isNativeCadSelector(selector) ? selector : "";
}

function selectorFromStepTreeInternalId(value) {
  const normalizedValue = String(value || "").trim();
  if (!normalizedValue.startsWith(STEP_TREE_TOPOLOGY_NODE_PREFIX)) {
    return "";
  }
  return nativeCadSelectorCandidate(normalizedValue.split(":").pop());
}

function canonicalCopyTextForSelector(value, { allowOpaque = false } = {}) {
  const normalizedValue = String(value || "").trim();
  if (!normalizedValue) {
    return "";
  }
  if (normalizedValue.startsWith("#")) {
    return canonicalCadRefCopyText(normalizedValue);
  }
  const selector = selectorFromStepTreeInternalId(normalizedValue) || normalizedValue;
  if (!allowOpaque && !nativeCadSelectorCandidate(selector)) {
    return "";
  }
  return `#${selector}`;
}

function canonicalCopyTextFromCandidates(candidates) {
  for (const candidate of Array.isArray(candidates) ? candidates : []) {
    const copyText = canonicalCopyTextForSelector(candidate?.value, {
      allowOpaque: candidate?.allowOpaque === true
    });
    if (copyText) {
      return copyText;
    }
  }
  return "";
}

function stepTreeNodeSelectorIdForWorkspace(node) {
  return [
    node?.displaySelector,
    node?.occurrenceId,
    node?.sourceOccurrenceId,
    node?.sourceRootTargetOccurrenceId,
    node?.id
  ].map(nativeCadSelectorCandidate).find(Boolean) || "";
}

function findStepTreeNodeForWorkspace(root, nodeId) {
  const normalizedNodeId = String(nodeId || "").trim();
  if (!root || !normalizedNodeId) {
    return null;
  }
  const stack = [root];
  while (stack.length) {
    const node = stack.pop();
    if (
      stepTreeNodeIdForWorkspace(node) === normalizedNodeId ||
      stepTreeNodeSelectorIdForWorkspace(node) === normalizedNodeId ||
      String(node?.name || "").trim() === normalizedNodeId ||
      String(node?.label || "").trim() === normalizedNodeId ||
      String(node?.displayName || "").trim() === normalizedNodeId
    ) {
      return node;
    }
    const children = stepTreeNodeChildren(node);
    for (let index = children.length - 1; index >= 0; index -= 1) {
      stack.push(children[index]);
    }
  }
  return null;
}

function collectStepTreeTopologyLoadableNodeIds(root) {
  const ids = [];
  const stack = root ? [root] : [];
  while (stack.length) {
    const node = stack.pop();
    const children = stepTreeNodeChildren(node);
    for (let index = children.length - 1; index >= 0; index -= 1) {
      stack.push(children[index]);
    }
    const nodeId = stepTreeNodeIdForWorkspace(node);
    if (
      nodeId &&
      String(node?.nodeType || "").trim() === "part" &&
      children.length === 0
    ) {
      ids.push(nodeId);
    }
  }
  return uniqueStringList(ids);
}

function copyableStepTreeNodeForWorkspace({ assemblyPartMap, displayStepTreeRoot, stepTreeRoot, nodeId }) {
  const normalizedNodeId = String(nodeId || "").trim();
  if (!normalizedNodeId) {
    return null;
  }
  return assemblyPartMap.get(normalizedNodeId) ||
    findStepTreeNodeForWorkspace(displayStepTreeRoot, normalizedNodeId) ||
    findStepTreeNodeForWorkspace(stepTreeRoot, normalizedNodeId) ||
    findAssemblyNode(displayStepTreeRoot, normalizedNodeId) ||
    findAssemblyNode(stepTreeRoot, normalizedNodeId) ||
    null;
}

function copyableAssemblyPartForSelection(part, fallbackId) {
  const fallbackSelector = nativeCadSelectorCandidate(fallbackId);
  const selector = [
    fallbackSelector,
    part?.displaySelector,
    part?.occurrenceId,
    part?.sourceOccurrenceId,
    part?.sourceRootTargetOccurrenceId,
    part?.id
  ].map(nativeCadSelectorCandidate).find(Boolean) || "";
  if (!selector) {
    return null;
  }
  return {
    ...(part || {}),
    id: String(part?.id || selector).trim(),
    displaySelector: selector,
    occurrenceId: selector,
    name: String(part?.name || part?.label || part?.displayName || selector).trim()
  };
}

function copyReferenceForAssemblyPartSelection(part, fallbackId) {
  const copyablePart = copyableAssemblyPartForSelection(part, fallbackId);
  const selector = String(copyablePart?.occurrenceId || copyablePart?.id || fallbackId || "").trim();
  if (!selector) {
    return null;
  }
  return {
    id: `assembly-part:${String(copyablePart?.id || selector).trim()}`,
    copyText: buildCadRefToken({ selector })
  };
}

function copyReferenceForRawSelectorSelection(selector, idPrefix = "selector-ref") {
  const copyText = canonicalCopyTextForSelector(selector);
  if (!copyText) {
    return null;
  }
  const normalizedSelector = copyText.slice(1);
  return {
    id: `${idPrefix}:${normalizedSelector}`,
    copyText
  };
}

function copyReferenceForStepTreeNodeSelection(node, fallbackId, idPrefix = "step-tree") {
  const nodeType = String(node?.nodeType || "").trim();
  const topologyNode = nodeType.startsWith("topology-");
  const copyText = canonicalCopyTextFromCandidates(topologyNode
    ? [
        { value: node?.displaySelector, allowOpaque: true },
        { value: node?.topologyReferenceId, allowOpaque: true },
        { value: fallbackId, allowOpaque: false },
        { value: node?.id, allowOpaque: false }
      ]
    : [
        { value: node?.displaySelector, allowOpaque: true },
        { value: node?.occurrenceId, allowOpaque: true },
        { value: node?.sourceOccurrenceId, allowOpaque: true },
        { value: node?.sourceRootTargetOccurrenceId, allowOpaque: true },
        { value: fallbackId, allowOpaque: false },
        { value: node?.id, allowOpaque: false }
      ]);
  if (!copyText) {
    return null;
  }
  const selector = copyText.slice(1);
  return {
    id: `${idPrefix}:${selector}`,
    copyText
  };
}

function addStepTreeCopyReferenceMapEntry(map, key, reference) {
  const normalizedKey = String(key || "").trim();
  if (!normalizedKey || !reference || map.has(normalizedKey)) {
    return;
  }
  map.set(normalizedKey, reference);
}

function buildStepTreeCopyReferenceMap(root) {
  const map = new Map();
  if (!root) {
    return map;
  }
  const stack = [root];
  while (stack.length) {
    const node = stack.pop();
    const nodeId = stepTreeNodeIdForWorkspace(node);
    const reference = copyReferenceForStepTreeNodeSelection(node, nodeId);
    if (reference) {
      addStepTreeCopyReferenceMapEntry(map, nodeId, reference);
      addStepTreeCopyReferenceMapEntry(map, node?.id, reference);
      addStepTreeCopyReferenceMapEntry(map, node?.topologyReferenceId, reference);
      addStepTreeCopyReferenceMapEntry(map, node?.displaySelector, reference);
      addStepTreeCopyReferenceMapEntry(map, node?.occurrenceId, reference);
      addStepTreeCopyReferenceMapEntry(map, node?.name, reference);
      addStepTreeCopyReferenceMapEntry(map, node?.label, reference);
      addStepTreeCopyReferenceMapEntry(map, node?.displayName, reference);
      addStepTreeCopyReferenceMapEntry(map, selectorFromStepTreeInternalId(node?.id), reference);
      addStepTreeCopyReferenceMapEntry(map, reference.copyText, reference);
      addStepTreeCopyReferenceMapEntry(map, reference.copyText.slice(1), reference);
    }
    const children = stepTreeNodeChildren(node);
    for (let index = children.length - 1; index >= 0; index -= 1) {
      stack.push(children[index]);
    }
  }
  return map;
}

function selectedCopyLinesFromIds(ids, copyReferenceMap) {
  const lines = [];
  const seen = new Set();
  for (const id of Array.isArray(ids) ? ids : []) {
    const normalizedId = String(id || "").trim();
    const copyText = canonicalCadRefCopyText(copyReferenceMap?.get(normalizedId)?.copyText) ||
      canonicalCopyTextForSelector(normalizedId);
    if (!copyText || seen.has(copyText)) {
      continue;
    }
    seen.add(copyText);
    lines.push(copyText);
  }
  return lines;
}

function copyPayloadWithSelectedIdFallback(
  payload,
  {
    selectedReferenceIds = [],
    selectedPartIds = [],
    copyReferenceMap = null
  } = {}
) {
  const currentLines = Array.isArray(payload?.lines)
    ? payload.lines.map((line) => canonicalCadRefCopyText(line)).filter(Boolean)
    : [];
  if (currentLines.length) {
    return {
      ...(payload || {}),
      lines: uniqueStringList(currentLines),
      copiedCount: payload?.copiedCount || currentLines.length
    };
  }
  const fallbackLines = uniqueStringList([
    ...selectedCopyLinesFromIds(selectedReferenceIds, copyReferenceMap),
    ...selectedCopyLinesFromIds(selectedPartIds, copyReferenceMap)
  ]);
  return {
    ...(payload || {}),
    lines: fallbackLines,
    copiedCount: fallbackLines.length || payload?.copiedCount || 0
  };
}

function addReferenceLookupKeys(map, reference) {
  if (!(map instanceof Map) || !reference) {
    return;
  }
  const keys = [
    reference?.id,
    reference?.normalizedSelector,
    reference?.displaySelector
  ].map((value) => String(value || "").trim()).filter(Boolean);
  const canonicalCopyText = canonicalCadRefCopyText(reference?.copyText);
  if (canonicalCopyText.startsWith("#")) {
    keys.push(canonicalCopyText);
    for (const selector of canonicalCopyText.slice(1).split(",")) {
      const normalizedSelector = String(selector || "").trim();
      if (normalizedSelector) {
        keys.push(normalizedSelector);
      }
    }
  }
  for (const key of keys) {
    if (!map.has(key)) {
      map.set(key, reference);
    }
  }
}

function stepTreeRootRowIsElidedForWorkspace(root, isAssemblyView) {
  const children = stepTreeNodeChildren(root);
  return children.length > 0 && (
    isAssemblyView ||
    stepTreeNodeIdForWorkspace(root) === STEP_MODEL_ROOT_ID
  );
}

function expandableStepTreeNodeIdsForWorkspace(root, {
  omitRoot = false,
  expandedTreeNodeIds = [],
  loadableTreeNodeIds = []
} = {}) {
  if (!root) {
    return [];
  }
  const ids = [];
  const seen = new Set();
  const loadableTreeNodeIdSet = new Set(
    (Array.isArray(loadableTreeNodeIds) ? loadableTreeNodeIds : [])
      .map((id) => String(id || "").trim())
      .filter(Boolean)
  );
  const visibleRows = flattenVisibleStepTreeRows(root, expandedTreeNodeIds, {
    omitRoot,
    showAllRootChildren: true
  });
  for (const row of visibleRows) {
    const node = row?.node || row;
    const nodeId = String(row?.id || "").trim() || stepTreeNodeIdForWorkspace(node);
    if (!nodeId || seen.has(nodeId)) {
      continue;
    }
    if (row?.hasChildren || stepTreeNodeChildren(node).length || loadableTreeNodeIdSet.has(nodeId)) {
      seen.add(nodeId);
      ids.push(nodeId);
    }
  }
  return ids;
}

function buildStepTreeExpansionMenuState({
  root,
  isAssemblyView = false,
  expandedTreeNodeIds = [],
  loadableTreeNodeIds = [],
  actionNodeIds = []
} = {}) {
  const expandedTreeNodeIdSet = new Set(
    (Array.isArray(expandedTreeNodeIds) ? expandedTreeNodeIds : [])
      .map((id) => String(id || "").trim())
      .filter(Boolean)
  );
  const normalizedActionNodeIds = uniqueStringList(
    (Array.isArray(actionNodeIds) ? actionNodeIds : [])
      .map((id) => String(id || "").trim())
      .filter(Boolean)
  );
  const actionRows = normalizedActionNodeIds
    .map((nodeId) => findStepTreeNodeForWorkspace(root, nodeId))
    .filter(Boolean);
  const collapsedActionNodeIds = actionRows
    .filter((row) => (
      (
        stepTreeNodeChildren(row).length ||
        loadableTreeNodeIds.includes(stepTreeNodeIdForWorkspace(row))
      ) &&
      !expandedTreeNodeIdSet.has(stepTreeNodeIdForWorkspace(row))
    ))
    .map((row) => stepTreeNodeIdForWorkspace(row))
    .filter(Boolean);
  const expandedActionNodeIds = actionRows
    .filter((row) => (
      (
        stepTreeNodeChildren(row).length ||
        loadableTreeNodeIds.includes(stepTreeNodeIdForWorkspace(row))
      ) &&
      expandedTreeNodeIdSet.has(stepTreeNodeIdForWorkspace(row))
    ))
    .map((row) => stepTreeNodeIdForWorkspace(row))
    .filter(Boolean);
  const expandableTreeNodeIds = expandableStepTreeNodeIdsForWorkspace(root, {
    omitRoot: stepTreeRootRowIsElidedForWorkspace(root, isAssemblyView),
    expandedTreeNodeIds,
    loadableTreeNodeIds
  });
  const collapsedExpandableTreeNodeIds = expandableTreeNodeIds
    .filter((nodeId) => !expandedTreeNodeIdSet.has(nodeId));
  const expandedExpandableTreeNodeIds = expandableTreeNodeIds
    .filter((nodeId) => expandedTreeNodeIdSet.has(nodeId));
  return {
    collapsedActionNodeIds,
    expandedActionNodeIds,
    collapsedExpandableTreeNodeIds,
    expandedExpandableTreeNodeIds,
    showExpandCollapse: Boolean(
      actionRows.some((row) => stepTreeNodeChildren(row).length) ||
      expandableTreeNodeIds.length
    )
  };
}

function visibleStepTreeTopologyReferenceIdsForWorkspace(root, expandedTreeNodeIds, {
  isAssemblyView = false
} = {}) {
  if (!root) {
    return [];
  }
  return uniqueStringList(
    flattenVisibleStepTreeRows(root, expandedTreeNodeIds, {
      omitRoot: stepTreeRootRowIsElidedForWorkspace(root, isAssemblyView),
      showAllRootChildren: true
    })
      .map((row) => String(row?.topologyReferenceId || "").trim())
      .filter(Boolean)
  );
}

function findStepTreeTopologyNodeIdForReference(root, referenceId) {
  const normalizedReferenceId = String(referenceId || "").trim();
  if (!root || !normalizedReferenceId) {
    return "";
  }
  const stack = [root];
  while (stack.length) {
    const node = stack.pop();
    if (String(node?.topologyReferenceId || "").trim() === normalizedReferenceId) {
      return stepTreeNodeIdForWorkspace(node);
    }
    const children = stepTreeNodeChildren(node);
    for (let index = children.length - 1; index >= 0; index -= 1) {
      stack.push(children[index]);
    }
  }
  return "";
}

function childAssemblyNodeIdForPickedLeaf(node, leafPartId) {
  const normalizedLeafPartId = String(leafPartId || "").trim();
  const children = Array.isArray(node?.children) ? node.children : [];
  if (!normalizedLeafPartId || !children.length) {
    return "";
  }
  for (const child of children) {
    const childId = String(child?.id || "").trim();
    if (!childId) {
      continue;
    }
    if (childId === normalizedLeafPartId) {
      return childId;
    }
    if (descendantLeafPartIds(child).includes(normalizedLeafPartId)) {
      return childId;
    }
  }
  return "";
}

function collectTopologyWrapperExpansionIds(node) {
  const expansionIds = [];
  const stack = [...stepTreeNodeChildren(node)].reverse();
  while (stack.length) {
    const child = stack.pop();
    const childId = stepTreeNodeIdForWorkspace(child);
    const childType = String(child?.nodeType || "").trim();
    const children = stepTreeNodeChildren(child);
    if (childType.startsWith("topology-") && childId && children.length && child?.visualOnly !== true) {
      expansionIds.push(childId);
    }
    for (let index = children.length - 1; index >= 0; index -= 1) {
      stack.push(children[index]);
    }
  }
  return expansionIds;
}

function collectStepTreeRevealExpansionIds(root, nodeId, {
  expandSelf = false,
  includeVisualOnlyAncestors = true
} = {}) {
  const normalizedNodeId = String(nodeId || "").trim();
  if (!root || !normalizedNodeId) {
    return [];
  }
  const node = findStepTreeNodeForWorkspace(root, normalizedNodeId);
  const expansionIds = collectStepTreeAncestorIds(root, normalizedNodeId)
    .filter((id) => {
      if (includeVisualOnlyAncestors) {
        return true;
      }
      const ancestor = findStepTreeNodeForWorkspace(root, id);
      return ancestor?.visualOnly !== true;
    });
  if (expandSelf && node && stepTreeNodeChildren(node).length) {
    expansionIds.push(normalizedNodeId, ...collectTopologyWrapperExpansionIds(node));
  }
  return [...new Set(expansionIds.filter(Boolean))];
}

function collectStepTreeSubtreeIds(root, nodeId) {
  const normalizedNodeId = String(nodeId || "").trim();
  const node = findStepTreeNodeForWorkspace(root, normalizedNodeId);
  if (!node) {
    return normalizedNodeId ? [normalizedNodeId] : [];
  }
  const ids = [];
  const stack = [node];
  while (stack.length) {
    const current = stack.pop();
    const currentId = stepTreeNodeIdForWorkspace(current);
    if (currentId) {
      ids.push(currentId);
    }
    const children = stepTreeNodeChildren(current);
    for (let index = children.length - 1; index >= 0; index -= 1) {
      stack.push(children[index]);
    }
  }
  return ids;
}

// The values throttled here are rebuilt objects — a useMemo over animation
// state, a map of parameter values — so their identity churns on renders where
// nothing about their contents changed. Comparing by identity made this hook
// re-emit values that were already current, and since an emit is itself a state
// update that causes the next render, each redundant emit bought another render
// of the whole workspace. Emit on a change of value, not of identity.
function throttledValuesEqual(left, right) {
  if (Object.is(left, right)) {
    return true;
  }
  const bothPlainObjects = left && right &&
    typeof left === "object" && typeof right === "object" &&
    !Array.isArray(left) && !Array.isArray(right);
  return bothPlainObjects ? shallowObjectValuesEqual(left, right) : false;
}

// React re-invokes state updaters, and it only stops re-rendering when the
// result is Object.is-equal to what it already has. The animation state
// updaters each built a fresh object every invocation, so a single click could
// be re-applied indefinitely: identical values, a new identity each time, never
// settling. Re-publishing the object already in the ref gives React the
// identity it needs to bail out, and keeps the ref write the animation tick
// depends on (it reads the ref synchronously between renders).
function publishAnimationState(stateRef, current, nextState) {
  const published = stateRef.current;
  if (published && shallowObjectValuesEqual(published, nextState)) {
    return published;
  }
  stateRef.current = nextState;
  return nextState;
}

function useThrottledValue(value, intervalMs, resetKey = "") {
  const [throttledValue, setThrottledValue] = useState(value);
  const latestValueRef = useRef(value);
  const lastEmittedRef = useRef(value);
  const resetKeyRef = useRef(resetKey);
  const lastEmitTimeRef = useRef(0);
  const timerIdRef = useRef(0);

  const emitValue = useCallback((nextValue) => {
    if (throttledValuesEqual(lastEmittedRef.current, nextValue)) {
      return;
    }
    lastEmittedRef.current = nextValue;
    setThrottledValue(nextValue);
  }, []);

  useEffect(() => {
    return () => {
      if (timerIdRef.current) {
        window.clearTimeout(timerIdRef.current);
        timerIdRef.current = 0;
      }
    };
  }, []);

  useEffect(() => {
    latestValueRef.current = value;
    const now = typeof performance !== "undefined" && typeof performance.now === "function"
      ? performance.now()
      : Date.now();
    const interval = Math.max(Number(intervalMs) || 0, 0);

    if (resetKeyRef.current !== resetKey) {
      resetKeyRef.current = resetKey;
      if (timerIdRef.current) {
        window.clearTimeout(timerIdRef.current);
        timerIdRef.current = 0;
      }
      lastEmitTimeRef.current = now;
      lastEmittedRef.current = value;
      setThrottledValue(value);
      return;
    }

    if (interval <= 0 || typeof window === "undefined") {
      lastEmitTimeRef.current = now;
      emitValue(value);
      return;
    }

    const elapsed = now - lastEmitTimeRef.current;
    if (elapsed >= interval) {
      if (timerIdRef.current) {
        window.clearTimeout(timerIdRef.current);
        timerIdRef.current = 0;
      }
      lastEmitTimeRef.current = now;
      emitValue(value);
      return;
    }

    if (!timerIdRef.current) {
      timerIdRef.current = window.setTimeout(() => {
        timerIdRef.current = 0;
        lastEmitTimeRef.current = typeof performance !== "undefined" && typeof performance.now === "function"
          ? performance.now()
          : Date.now();
        emitValue(latestValueRef.current);
      }, interval - elapsed);
    }
  }, [emitValue, intervalMs, resetKey, value]);

  return throttledValue;
}

// Hide an entry's render assets (url/hash/bytes/assets) so the viewer treats it as "not yet
// renderable" — used while its render artifact is missing/stale/building or has failed, so the
// viewer shows a loading/error state and never renders a stale cache. Once the artifact is ready
// the unstripped catalog entry is used and the mesh loads.
function entryWithoutRenderAssets(entry) {
  if (!entry) {
    return entry;
  }
  const next = { ...entry };
  delete next.url;
  delete next.hash;
  delete next.bytes;
  delete next.assets;
  // A baked mesh published as a `glb` relation rather than as the entry's own url would
  // otherwise stay renderable while its replacement is being built -- which is exactly the
  // stale cache this function exists to hide.
  if (next.relations?.glb) {
    const relations = { ...next.relations };
    delete relations.glb;
    next.relations = relations;
  }
  return next;
}

function scopedWorkspacePerspective(snapshot, modelKey, entry) {
  const normalized = clonePerspectiveSnapshot(snapshot);
  if (!normalized) {
    return null;
  }
  const sceneScaleMode = renderCapabilities(entrySourceFormat(entry)).sceneScale;
  return annotatePerspectiveSnapshot(normalized, {
    modelKey,
    sceneScaleMode,
    coordinateSystem: sceneScaleMode === "urdf" ? "cad-z-up-robot-framing-v2" : "cad-z-up-v1"
  });
}

export default function CadWorkspace({
  manifestEntries: manifestEntriesProp = [],
  manifestRevision = 0,
  catalogHydrated = false,
  catalogRefreshing = false,
  catalogError = "",
}) {
  // Scene presets do not change the app's chrome. System follows this
  // independently persisted preference, resolved against the live OS mode.
  const systemPrefersDark = useSystemPrefersDark();
  const [colorSchemePreference, setColorSchemePreference] = useState(readColorSchemePreference);
  const resolvedColorSchemeMode = resolveColorSchemeMode(colorSchemePreference, {
    prefersDark: systemPrefersDark
  });
  const uiPrefersDark = resolvedColorSchemeMode === DARK_COLOR_SCHEME_ID;
  const chromeBackdropColor = useChromeBackdropColor(uiPrefersDark);
  const manifestEntries = Array.isArray(manifestEntriesProp) ? manifestEntriesProp : [];
  const catalogEntries = manifestEntries;
  const explicitFileParam = readCadParam();
  // Session state is namespaced per origin, and an origin (host + port) is one viewer
  // serving one root. This used to be keyed on the directory in the URL path, back when
  // one instance could show any folder.
  const catalogRootDir = "";
  const [query, setQuery] = useState("");
  const initialFileViewerDirectoryStateRef = useRef(null);
  if (!initialFileViewerDirectoryStateRef.current) {
    const storedExpandedDirectoryIds = readDirectorySessionState().fileViewerExpandedDirectoryIds;
    initialFileViewerDirectoryStateRef.current = {
      hasStoredState: Array.isArray(storedExpandedDirectoryIds),
      expandedDirectoryIds: Array.isArray(storedExpandedDirectoryIds) ? storedExpandedDirectoryIds : []
    };
  }
  const [expandedDirectoryIds, setExpandedDirectoryIds] = useState(() => (
    new Set(initialFileViewerDirectoryStateRef.current.expandedDirectoryIds)
  ));
  const [fileViewerDirectoryStateInitialized, setFileViewerDirectoryStateInitialized] = useState(() => (
    initialFileViewerDirectoryStateRef.current.hasStoredState
  ));
  const [openTabs, setOpenTabs] = useState([]);
  const [viewerServerInfo, setViewerServerInfo] = useState(null);
  // Development only: a cadgen running from a source checkout restarts itself
  // on its own port when its Python changes, and this reloads the page once it
  // is back. An installed wheel reports autoReload:false and never polls.
  const viewerReloading = useViewerAutoReload(viewerServerInfo);
  const viewerServerBackend = String(viewerServerInfo?.backend || "").trim().toLowerCase();
  const [selectedKey, setSelectedKey] = useState("");
  const [fileSheetOpenSectionIds, setFileSheetOpenSectionIds] = useState(null);
  const [dxfThicknessMm, setDxfThicknessMm] = useState(0);
  const [dxfBendSettings, setDxfBendSettings] = useState([]);
  const [dxfViewMode, setDxfViewMode] = useState("2d");
  const [referenceQuery, setReferenceQuery] = useState("");
  const [selectedReferenceIds, setSelectedReferenceIds] = useState([]);
  const [largeFileState, setLargeFileState] = useState(() => normalizeLargeFileState(DEFAULT_LARGE_FILE_STATE));
  // Capability demand is scoped to the artifact the user acted on. The
  // default Select tool alone does not imply topology work during file open.
  const [requestedTopologyFileRef, setRequestedTopologyFileRef] = useState("");
  const pendingModelReferenceActivationRef = useRef(null);
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
  const [sidebarOpen, setSidebarOpen] = useState(() => (
    readDirectorySessionState().fileViewerOpen
  ));
  const [sidebarWidth, setSidebarWidth] = useState(() => (
    readDirectorySessionState().fileViewerWidthPx || DEFAULT_SIDEBAR_WIDTH
  ));
  const [layoutViewportWidth, setLayoutViewportWidth] = useState(readViewerViewportWidth);
  const isDesktop = viewerLayoutMode === CAD_WORKSPACE_LAYOUT_MODE.DESKTOP;
  const [fileSheetOpenIntent, setFileSheetOpenIntent] = useState(readInitialFileSheetOpen);
  const [viewerAlertOpen, setViewerAlertOpen] = useState(false);
  const [viewerRuntimeAlert, setViewerRuntimeAlert] = useState(null);
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
  const renderVisualKey = renderVisualSettingsKey(renderSession.payload);
  const resolvedVisualScene = useMemo(() => resolveSceneSettings({
    appearance: colorSchemePreference,
    prefersDark: systemPrefersDark,
    render: renderSession.enabled ? renderVisualPayload(renderSession.payload) : null,
    display: renderSession.enabled ? null : displaySettings
  }), [
    colorSchemePreference,
    displaySettings,
    renderSession.enabled,
    renderVisualKey,
    systemPrefersDark
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
      appearance: colorSchemePreference,
      prefersDark: systemPrefersDark,
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
    colorSchemePreference,
    renderSession.enabled,
    renderSession.payload.quality,
    renderVisualKey,
    resolvedCamera,
    resolvedVisualScene.render.configuration,
    systemPrefersDark
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
  const [tabToolsWidth, setTabToolsWidth] = useState(readInitialFileSheetWidth);
  const [fileSheetWidthIsCustom, setFileSheetWidthIsCustom] = useState(readInitialFileSheetWidthIsCustom);
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
  const [stepModuleEnabled, setStepModuleEnabled] = useState(true);
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

  const entryMap = useMemo(() => {
    const map = new Map();
    for (const entry of catalogEntries) {
      map.set(fileKey(entry), entry);
    }
    return map;
  }, [catalogEntries]);
  const fileSessionNamespace = useMemo(
    () => normalizeFileSessionNamespace(catalogRootDir),
    [catalogRootDir]
  );

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
    entryHasMesh,
    entryHasReferences,
    entryHasDisplayEdges,
    buildNormalizedReferenceState,
  });

  const filteredEntries = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) {
      return catalogEntries;
    }
    return catalogEntries.filter((entry) => {
      return (
        sidebarLabelForEntry(entry).toLowerCase().includes(q) ||
        String(entry.kind || "").toLowerCase().includes(q) ||
        fileKey(entry).toLowerCase().includes(q)
      );
    });
  }, [catalogEntries, query]);
  const allEntriesTree = useMemo(
    () => buildSidebarDirectoryTree(catalogEntries),
    [catalogEntries]
  );
  const filteredEntriesTree = useMemo(
    () => buildSidebarDirectoryTree(filteredEntries),
    [filteredEntries]
  );
  const allDirectoryIds = useMemo(() => collectSidebarDirectoryIds(allEntriesTree), [allEntriesTree]);

  const catalogSelectedEntry = entryMap.get(selectedKey) ?? null;
  const selectedCatalogPending = catalogSelectedEntry?.catalogPending === true;
  const selectedCatalogFile = fileKey(catalogSelectedEntry);
  useEffect(() => {
    if (selectedCatalogPending && selectedCatalogFile) {
      refreshCadCatalog({ fileRef: selectedCatalogFile, markRefreshing: false }).catch(() => {});
    }
  }, [selectedCatalogPending, selectedCatalogFile]);
  const explicitFileEntry = explicitFileParam ? findEntryByUrlPath(catalogEntries, explicitFileParam) : null;
  const fileParamSelectionPending = shouldDeferFileParamSelection({
    explicitFileParam,
    matchingEntry: explicitFileEntry,
    selectedEntry: catalogSelectedEntry,
    catalogHydrated,
    catalogRefreshing
  });
  const missingFileRef = catalogError
    ? ""
    : missingFileRefForCatalog({
        explicitFileParam,
        matchingEntry: explicitFileEntry,
        selectedEntry: catalogSelectedEntry,
        catalogHydrated,
        catalogRefreshing
      });
  const catalogSelectedEntrySourceFormat = entrySourceFormat(catalogSelectedEntry);
  const editingFile = catalogSelectedEntry ? fileKey(catalogSelectedEntry) : explicitFileParam;
  const editingAvailable = /\.st(?:ep|p)$/i.test(editingFile || "");
  const editingPreview = useEditingPreview(editingFile, {
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
    catalogSelectedEntry ? fileKey(catalogSelectedEntry) : "",
    {
      enabled: !selectedCatalogPending && isArtifactManagedFormat(catalogSelectedEntrySourceFormat),
      freshnessKey: `${catalogSelectedEntry?.hash || ""}:${manifestRevision}`,
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
    () => shortestUniquePathSuffixes(catalogEntries.map((entry) => cadFileParamForEntry(entry))),
    [catalogEntries]
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
      pendingModelReferenceActivationRef.current = null;
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
    if (typeof window === "undefined") {
      return undefined;
    }
    const controller = new AbortController();
    let active = true;
    const url = new URL("/__cad/server", window.location.href);
    const activeFile = readCadParam();
    if (activeFile) {
      url.searchParams.set("file", activeFile);
    }
    fetch(`${url.pathname}${url.search}`, {
      cache: "no-store",
      signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok) {
        throw new Error(`Failed to read CAD Viewer server info: ${response.status} ${response.statusText}`);
      }
      return response.json();
    }).then((payload) => {
      if (active) {
        setViewerServerInfo(payload && typeof payload === "object" ? payload : {});
      }
    }).catch((error) => {
      if (active && error?.name !== "AbortError") {
        setViewerServerInfo({});
      }
    });
    return () => {
      active = false;
      controller.abort();
    };
  }, [catalogRootDir, explicitFileParam]);


  useEffect(() => {
    let cancelled = false;
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
          cadPath: selectedStepModuleCadPath, documentHash: selectedEntry?.documentHash,
        });
    modulePromise.then((definition) => {
      if (cancelled) {
        return;
      }
      const restoredSessionState = readFileSessionState(
        fileSessionNamespace,
        fileKey(selectedEntry),
        selectedEntry
      );
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
    };
  }, [fileSessionNamespace, selectedEntry, selectedStepModuleCadPath, selectedStepModuleUrl]);

  // The animation half compiles the exact source embedded in the selected
  // sidecar. A document with no animation resolves to no clips and no
  // Animation tab, and a broken one reports its own error without disturbing
  // the Pose tab.
  useEffect(() => {
    let cancelled = false;
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
        const restoredSessionState = readFileSessionState(
          fileSessionNamespace,
          fileKey(selectedEntry),
          selectedEntry
        );
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
    () => robotComponents(selectedUrdfMeshGeometryResult.meshData, selectedUrdfFileRef),
    [selectedUrdfMeshGeometryResult.meshData, selectedUrdfFileRef]
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
    !renderSession.enabled && stepModuleEnabled && selectedStepModuleTopologyRequired;
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
  const requestedStepTreeTopologyNodeIds = useMemo(() => {
    if (!supportsTopology || !isAssemblyView || !selectedEntryHasReferences) {
      return [];
    }
    return uniqueStringList(
      [
        ...expandedStepTreeNodeIds,
        ...(stepModuleEnabled ? stepModuleTopologyOccurrenceIds(selectedStepModuleDefinition) : [])
      ]
        .map((id) => String(id || "").trim())
        .filter((id) => id && loadableStepTreeTopologyNodeIdSet.has(id))
    );
  }, [
    expandedStepTreeNodeIds,
    isAssemblyView,
    supportsTopology,
    loadableStepTreeTopologyNodeIdSet,
    selectedStepModuleDefinition,
    selectedEntryHasReferences,
    stepModuleEnabled,
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
  const viewerLoadingFiles = useMemo(
    () => (effectiveViewerLoading && catalogSelectedEntry ? [fileKey(catalogSelectedEntry)] : []),
    [effectiveViewerLoading, catalogSelectedEntry]
  );
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
  // This is the displayed render revision, so same-file saves cannot inherit
  // a predecessor's scheduler or benchmark milestones.
  const viewportQualityModelKey = `${selectedEntry?.file || ""}:${selectedMeshHash || selectedEntry?.hash || ""}`;
  // Viewport LOD (design/unified-tessellation.md Phase 5): camera-settle
  // driven re-tessellation of the components that project the worst error.
  const { onCameraMoved: onLodCameraMoved } = useViewportLod({
    viewerRef,
    modelKey: viewportQualityModelKey,
    quality: resolvedScene.quality,
    lodPackage,
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
  const panelResizeStateRef = useRef(null);
  const fileSessionSaveTimerRef = useRef(0);
  const openTabsRef = useRef(openTabs);
  const activePerspectiveRef = useRef(null);
  const tabToolsResizeStateRef = useRef(null);
  const selectedFileSheetKeyRef = useRef("");
  const cadDirectorySessionBootstrappedRef = useRef(false);

  useEffect(() => {
    openTabsRef.current = openTabs;
  }, [openTabs]);

  const tabToolsOpen = fileSheetOpenIntent;
  const fileViewerExpandedDirectoryIdList = useMemo(() => (
    [...expandedDirectoryIds].sort((a, b) => a.localeCompare(b, undefined, {
      numeric: true,
      sensitivity: "base"
    }))
  ), [expandedDirectoryIds]);
  const defaultFileSheetWidth = useMemo(
    () => cadWorkspaceDefaultFileSheetWidthForViewport(layoutViewportWidth),
    [layoutViewportWidth]
  );

  const setTabToolsOpen = useCallback((value) => {
    setFileSheetOpenIntent((current) => (
      typeof value === "function" ? value(current) : value
    ));
  }, []);
  useEffect(() => {
    writeCadDirectorySessionState({
      fileViewerOpen: sidebarOpen,
      fileViewerExpandedDirectoryIds: fileViewerDirectoryStateInitialized ? fileViewerExpandedDirectoryIdList : null,
      fileViewerWidthPx: sidebarWidth,
      fileSheetOpen: tabToolsOpen,
      fileSheetWidthPx: fileSheetWidthIsCustom ? tabToolsWidth : defaultFileSheetWidth
    }, {
      defaultFileSheetWidthPx: defaultFileSheetWidth,
      onWriteError: handlePersistenceWriteError
    });
  }, [
    defaultFileSheetWidth,
    fileViewerDirectoryStateInitialized,
    fileViewerExpandedDirectoryIdList,
    fileSheetWidthIsCustom,
    handlePersistenceWriteError,
    sidebarOpen,
    sidebarWidth,
    tabToolsOpen,
    tabToolsWidth
  ]);

  useEffect(() => {
    if (fileSheetWidthIsCustom) {
      return;
    }
    setTabToolsWidth(defaultFileSheetWidth);
  }, [defaultFileSheetWidth, fileSheetWidthIsCustom]);
  const desktopRightPanelOpen = isDesktop && !previewMode &&
    tabToolsOpen && !!selectedFileSheetKind && selectedFileSheetHasSections;
  const effectiveSidebarOpen = sidebarOpen && !previewMode;
  const desktopSidebarOpen = isDesktop && effectiveSidebarOpen && !previewMode;

  // DXF settings are PER FILE, remembered for the session: each drawing keeps its own
  // thickness/bends/style/layers in sessionStorage under its entry key, so switching files
  // never leaks one drawing's settings into another, and switching BACK restores what you
  // set. Session-scoped on purpose — nothing here may outlive the tab or invalidate a cache.
  //
  // Ordering matters: the persist effect is declared BEFORE the load effect and only writes
  // once the load effect has stamped the current key, so the commit that switches files can
  // never save the previous file's values under the new file's key.
  const drawingSettingsLoadedKeyRef = useRef(null);
  useEffect(() => {
    if (!selectedEntryIsDrawing || !selectedKey || drawingSettingsLoadedKeyRef.current !== selectedKey) {
      return;
    }
    try {
      window.sessionStorage?.setItem(
        `cadViewer.dxfSettings:${selectedKey}`,
        JSON.stringify({
          thicknessMm: drawingThicknessMm,
          bends: drawingBends,
          bendStyle: drawingBendStyle,
          bendRadiusMm: drawingBendRadiusMm,
          kFactor: drawingKFactor,
          hiddenLayers: drawingHiddenLayers,
          units: drawingUnits,
          orientation: drawingOrientation,
          material: drawingMaterial
        })
      );
    } catch (storageError) {
      // Quota or privacy mode: settings simply stop surviving a file switch.
    }
  }, [selectedEntryIsDrawing, selectedKey, drawingThicknessMm, drawingBends, drawingBendStyle, drawingBendRadiusMm, drawingKFactor, drawingHiddenLayers, drawingUnits, drawingOrientation, drawingMaterial]);

  useEffect(() => {
    let stored = null;
    if (selectedEntryIsDrawing && selectedKey) {
      try {
        const raw = window.sessionStorage?.getItem(`cadViewer.dxfSettings:${selectedKey}`);
        stored = raw ? JSON.parse(raw) : null;
      } catch (storageError) {
        stored = null;
      }
    }
    drawingSettingsLoadedKeyRef.current = selectedKey;
    setDrawingThicknessMm(normalizeDxfThicknessMm(stored?.thicknessMm, DXF_DEFAULT_THICKNESS_MM));
    setDrawingBendStyle(normalizeDxfBendStyle(stored?.bendStyle, DXF_DEFAULT_BEND_STYLE));
    setDrawingBendRadiusMm(normalizeDxfBendRadiusMm(stored?.bendRadiusMm, DXF_DEFAULT_BEND_RADIUS_MM));
    setDrawingKFactor(normalizeDxfKFactor(stored?.kFactor, DXF_DEFAULT_KFACTOR));
    setDrawingHiddenLayers(Array.isArray(stored?.hiddenLayers)
      ? stored.hiddenLayers.filter((name) => typeof name === "string")
      : []);
    setDrawingUnits(normalizeDxfUnits(stored?.units, DXF_DEFAULT_UNITS));
    setDrawingOrientation(normalizeDxfOrientation(stored?.orientation));
    setDrawingMaterial(normalizeDxfMaterial(stored?.material, DXF_DEFAULT_MATERIAL));
    setDrawingBends(Array.from({ length: selectedDrawingBendAxisCount }, (_, index) => ({
      angleDeg: normalizeDxfBendAngleDeg(stored?.bends?.[index]?.angleDeg, DXF_DEFAULT_BEND_ANGLE_DEG),
      direction: normalizeDxfBendDirection(stored?.bends?.[index]?.direction)
    })));
  }, [selectedKey, selectedDrawingBendAxisCount, selectedEntryIsDrawing]);

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

  const handleViewerAlertChange = useCallback((nextAlert) => {
    setViewerRuntimeAlert(nextAlert || null);
  }, []);

  const endPanelResize = useCallback(() => {
    document.querySelector("[data-slot='sidebar-wrapper']")?.removeAttribute("data-sidebar-resizing");
    panelResizeStateRef.current = null;
    if (!tabToolsResizeStateRef.current) {
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    }
  }, []);

  const endTabToolsResize = useCallback(() => {
    tabToolsResizeStateRef.current = null;
    if (!panelResizeStateRef.current) {
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    }
  }, []);

  const handleStartSidebarResize = useCallback((event) => {
    if (event.button !== 0) {
      return;
    }
    if (!isDesktop || !effectiveSidebarOpen) {
      return;
    }

    event.preventDefault();
    const nextWidth = resolveDesktopPanelWidths({
      viewportWidth: layoutViewportWidth,
      sidebarOpen: desktopSidebarOpen,
      sheetOpen: desktopRightPanelOpen,
      sidebarWidth,
      sheetWidth: tabToolsWidth,
      sidebarMinWidth: DESKTOP_SIDEBAR_MIN_WIDTH,
      sheetMinWidth: DESKTOP_TAB_TOOLS_MIN_WIDTH,
      sidebarMaxWidth: DESKTOP_SIDEBAR_MAX_WIDTH,
      sheetMaxWidth: DESKTOP_TAB_TOOLS_MAX_WIDTH
    }).sidebarWidth;
    document.querySelector("[data-slot='sidebar-wrapper']")?.setAttribute("data-sidebar-resizing", "true");
    panelResizeStateRef.current = {
      startX: event.clientX,
      startWidth: nextWidth,
      latestWidth: nextWidth
    };
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [
    desktopRightPanelOpen,
    desktopSidebarOpen,
    effectiveSidebarOpen,
    isDesktop,
    layoutViewportWidth,
    sidebarWidth,
    tabToolsWidth
  ]);

  const handleSidebarOpenChange = useCallback((value) => {
    setSidebarOpen((current) => {
      const nextOpen = typeof value === "function" ? value(current) : value;
      if (nextOpen && !isDesktop) {
        setTabToolsOpen(false);
      }
      if (!current && nextOpen) {
        setSidebarWidth((currentWidth) => {
          const numericWidth = Number(currentWidth);
          return Number.isFinite(numericWidth) && numericWidth >= DESKTOP_SIDEBAR_MIN_WIDTH
            ? currentWidth
            : DEFAULT_SIDEBAR_WIDTH;
        });
      }
      return nextOpen;
    });
  }, [isDesktop, setTabToolsOpen]);

  const handleStartFileSheetResize = useCallback((event) => {
    // Gate on the shared right-panel flag, not the file sheet specifically:
    // the settings sheet is the same panel and resizes to the same width.
    if (event.button !== 0 || !desktopRightPanelOpen) {
      return;
    }

    event.preventDefault();
    setFileSheetWidthIsCustom(true);
    const nextWidth = resolveDesktopPanelWidths({
      viewportWidth: layoutViewportWidth,
      sidebarOpen: desktopSidebarOpen,
      sheetOpen: desktopRightPanelOpen,
      sidebarWidth,
      sheetWidth: tabToolsWidth,
      sidebarMinWidth: DESKTOP_SIDEBAR_MIN_WIDTH,
      sheetMinWidth: DESKTOP_TAB_TOOLS_MIN_WIDTH,
      sidebarMaxWidth: DESKTOP_SIDEBAR_MAX_WIDTH,
      sheetMaxWidth: DESKTOP_TAB_TOOLS_MAX_WIDTH
    }).sheetWidth;
    tabToolsResizeStateRef.current = {
      startX: event.clientX,
      startWidth: nextWidth
    };
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [
    desktopRightPanelOpen,
    desktopSidebarOpen,
    layoutViewportWidth,
    sidebarWidth,
    setFileSheetWidthIsCustom,
    tabToolsWidth
  ]);

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

  const upsertTabRecord = useCallback((tabs, key, snapshot = null) => {
    if (!key) {
      return tabs;
    }

    const normalizedSnapshot = snapshot ? cloneTabSnapshot(snapshot) : null;
    const index = tabs.findIndex((tab) => tab.key === key);

    if (index === -1) {
      if (!normalizedSnapshot) {
        return [...tabs, createTabRecord(key)];
      }
      return [...tabs, createTabRecord(key, normalizedSnapshot)];
    }

    if (!normalizedSnapshot) {
      return tabs;
    }

    const current = tabs[index];
    if (tabSnapshotEqual(current, normalizedSnapshot)) {
      return tabs;
    }

    const next = [...tabs];
    next[index] = {
      key,
      ...normalizedSnapshot
    };
    return next;
  }, []);

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
      if (isDesktop) setTabToolsOpen(true);
      const revealIds = [FILE_SHEET_SECTION_IDS.STEP_REFERENCE, FILE_SHEET_SECTION_IDS.ROBOT_COMPONENTS];
      setFileSheetOpenSectionIds((current) => [
        ...(current || []).filter((sectionId) => !revealIds.includes(sectionId)),
        ...revealIds
      ]);
    }
  }, [robotSelection.select, selectedUrdfComponents, isDesktop]);

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
    const normalizedKey = String(key || "").trim();
    if (!normalizedKey) {
      return null;
    }
    return readFileSessionState(
      fileSessionNamespace,
      normalizedKey,
      entryOverride || entryMap.get(normalizedKey)
    );
  }, [entryMap, fileSessionNamespace]);

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
    return writeFileSessionState(
      fileSessionNamespace,
      targetFileKey,
      buildActiveFileSessionSnapshot(entry),
      { onWriteError: handlePersistenceWriteError }
    );
  }, [
    buildActiveFileSessionSnapshot,
    fileSessionNamespace,
    handlePersistenceWriteError
  ]);

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
          appearance: colorSchemePreference,
          prefersDark: systemPrefersDark,
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
    colorSchemePreference,
    entryMap,
    materialSession.restoreSlice,
    readEntrySessionState,
    systemPrefersDark
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
    setSelectedKey(nextTab.key);
  }, [entryMap, fileSheetSelectionKeyForTab]);

  const resetActiveDirectory = useCallback(() => {
    selectedReferenceIdsRef.current = [];
    selectedPartIdsRef.current = [];
    setSelectedWholeEntryCadRefToken("");
    setReferenceQuery("");
    setSelectedReferenceIds([]);
    setSelectedPartIds([]);
    setSelectedRenderPartIdByAssemblyPartId({});
    setExpandedStepTreeNodeIds([]);
    setFileSheetOpenSectionIds(null);
    setHiddenPartIds([]);
    setIsolatedAssemblyNodeIds([]);
    setDisplaySettings(normalizeDisplaySettings());
    setRenderSession(createRenderSessionState());
    materialSession.clearAll();
    setLargeFileState(normalizeLargeFileState(DEFAULT_LARGE_FILE_STATE));
    setHoveredListReferenceId("");
    setHoveredModelReferenceId("");
    setHoveredListPartId("");
    setHoveredModelPartId("");
    setCopyStatus("");
    setScreenshotStatus("");
    setTabToolsOpen(false);
    setTabToolMode(TAB_TOOL_MODE.REFERENCES);
    setDrawingTool(DRAWING_TOOL.FREEHAND);
    activePerspectiveRef.current = null;
    setViewerPerspective(null);
    setDrawingStrokes([]);
    setDrawingUndoStack([]);
    setDrawingRedoStack([]);
    setSelectedKey("");
  }, [materialSession.clearAll, setTabToolsOpen]);

  const activateEntryTab = useCallback((key) => {
    if (!key || !entryMap.has(key)) {
      return;
    }
    if (key === selectedKey) {
      return;
    }

    if (selectedKey) {
      flushActiveFileSession();
    }

    const nextTabs = openTabsRef.current;
    const nextEntry = entryMap.get(key);
    const restoredSessionState = readEntrySessionState(key, nextEntry);
    const restoredTabSnapshot = restoredSessionState?.slices?.tab || null;
    const nextTab = nextTabs.find((tab) => tab.key === key) || createTabRecord(key, {
      drawingTool: selectedKey ? drawingTool : DRAWING_TOOL.FREEHAND,
      tabToolMode: selectedKey ? tabToolMode : TAB_TOOL_MODE.REFERENCES,
      ...(restoredTabSnapshot || {})
    });
    const cachedMeshState = nextEntry ? getCachedMeshState(nextEntry) : null;
    const cachedReferenceState = nextEntry ? getCachedReferenceState(nextEntry) : null;
    const cachedUrdfState = nextEntry ? getCachedUrdfState(nextEntry) : null;
    const currentSnapshot = selectedKey ? buildActiveTabSnapshot() : null;

    setOpenTabs((current) => {
      let next = current;
      if (selectedKey) {
        next = upsertTabRecord(next, selectedKey, currentSnapshot);
      }
      next = upsertTabRecord(next, key, nextTab);
      return next;
    });

    if (!entryHasMesh(nextEntry)) {
      setStatus(ASSET_STATUS.PENDING);
      setError("");
    } else if (cachedMeshState) {
      setMeshState(cachedMeshState);
      setStatus(ASSET_STATUS.READY);
      setError("");
    }

    if (!entryHasReferences(nextEntry)) {
      setReferenceState(null);
      setReferenceStatus(REFERENCE_STATUS.DISABLED);
      setReferenceError("");
    } else if (cachedReferenceState) {
      setReferenceState(cachedReferenceState);
      setReferenceStatus(cachedReferenceState.disabledReason ? REFERENCE_STATUS.DISABLED : REFERENCE_STATUS.READY);
      setReferenceError(cachedReferenceState.disabledReason || "");
    }

    if (!entryHasUrdf(nextEntry)) {
      setUrdfState(null);
      setUrdfStatus(ASSET_STATUS.PENDING);
      setUrdfError("");
    } else if (cachedUrdfState) {
      setUrdfState(cachedUrdfState);
      setUrdfStatus(ASSET_STATUS.READY);
      setUrdfError("");
    }

    applyTabRecord(nextTab);
    applyEntrySessionState(key, restoredSessionState);
  }, [
    applyEntrySessionState,
    applyTabRecord,
    buildActiveTabSnapshot,
    drawingTool,
    entryMap,
    flushActiveFileSession,
    getCachedMeshState,
    getCachedReferenceState,
    getCachedUrdfState,
    readEntrySessionState,
    selectedKey,
    setUrdfError,
    setUrdfState,
    setUrdfStatus,
    tabToolMode,
    upsertTabRecord
  ]);

  const cadFileParamForSelectedEntry = useCallback(
    (entry) => cadFileParamForEntry(entry),
    []
  );

  useCadDirectorySession({
    manifestEntries,
    cadFileParamForEntry: cadFileParamForSelectedEntry,
    cadDirectorySessionBootstrappedRef,
    setOpenTabs,
    applyTabRecord,
    selectedEntryKeyFromUrl,
    createTabRecord,
    initialSelectedTabSnapshot: {
      drawingTool: DRAWING_TOOL.FREEHAND,
      tabToolMode: TAB_TOOL_MODE.REFERENCES
    },
    upsertTabRecord,
    selectedEntry,
    defaultDocumentTitle: DOCUMENT_TITLE,
    selectedKey,
    entryMap,
    buildActiveTabSnapshot,
    catalogEntries,
    manifestRevision,
    defaultSidebarWidth: DEFAULT_SIDEBAR_WIDTH,
    sidebarMinWidth: DESKTOP_SIDEBAR_MIN_WIDTH,
    readCadParam,
    activateEntryTab,
    resetActiveDirectory,
    writeCadParam,
    readEntrySessionState,
    applyEntrySessionState
  });

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
    applyColorSchemeToDocument(colorSchemePreference, document.documentElement, {
      prefersDark: systemPrefersDark
    });
  }, [colorSchemePreference, systemPrefersDark]);

  useEffect(() => {
    const syncColorSchemePreference = () => {
      setColorSchemePreference(readColorSchemePreference());
    };
    const handleStorage = (event) => {
      const action = cadDirectoryStorageEventAction(event.key);
      if (action === CAD_DIRECTORY_STORAGE_EVENT_ACTION.COLOR_SCHEME) {
        syncColorSchemePreference();
      }
    };
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        syncColorSchemePreference();
      }
    };

    window.addEventListener("storage", handleStorage);
    window.addEventListener("focus", syncColorSchemePreference);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      window.removeEventListener("storage", handleStorage);
      window.removeEventListener("focus", syncColorSchemePreference);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, []);

  const handleColorSchemePreferenceChange = useCallback((nextPreference) => {
    writeColorSchemePreference(nextPreference, { onWriteError: handlePersistenceWriteError });
    setColorSchemePreference(readColorSchemePreference());
  }, [handlePersistenceWriteError]);

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

  const resolvedDesktopPanelWidths = useMemo(() => resolveDesktopPanelWidths({
    viewportWidth: layoutViewportWidth,
    sidebarOpen: desktopSidebarOpen,
    sheetOpen: desktopRightPanelOpen,
    sidebarWidth,
    sheetWidth: tabToolsWidth,
    sidebarMinWidth: DESKTOP_SIDEBAR_MIN_WIDTH,
    sheetMinWidth: DESKTOP_TAB_TOOLS_MIN_WIDTH,
    sidebarMaxWidth: DESKTOP_SIDEBAR_MAX_WIDTH,
    sheetMaxWidth: DESKTOP_TAB_TOOLS_MAX_WIDTH
  }), [
    desktopRightPanelOpen,
    desktopSidebarOpen,
    layoutViewportWidth,
    sidebarWidth,
    tabToolsWidth
  ]);

  const clampSidebarWidth = useCallback((value) => {
    return resolveDesktopPanelWidths({
      viewportWidth: layoutViewportWidth,
      sidebarOpen: desktopSidebarOpen,
      sheetOpen: desktopRightPanelOpen,
      sidebarWidth: value,
      sheetWidth: tabToolsWidth,
      sidebarMinWidth: DESKTOP_SIDEBAR_MIN_WIDTH,
      sheetMinWidth: DESKTOP_TAB_TOOLS_MIN_WIDTH,
      sidebarMaxWidth: DESKTOP_SIDEBAR_MAX_WIDTH,
      sheetMaxWidth: DESKTOP_TAB_TOOLS_MAX_WIDTH
    }).sidebarWidth;
  }, [desktopRightPanelOpen, desktopSidebarOpen, layoutViewportWidth, tabToolsWidth]);

  const clampTabToolsWidth = useCallback((value) => {
    return resolveDesktopPanelWidths({
      viewportWidth: layoutViewportWidth,
      sidebarOpen: desktopSidebarOpen,
      sheetOpen: desktopRightPanelOpen,
      sidebarWidth,
      sheetWidth: value,
      sidebarMinWidth: DESKTOP_SIDEBAR_MIN_WIDTH,
      sheetMinWidth: DESKTOP_TAB_TOOLS_MIN_WIDTH,
      sidebarMaxWidth: DESKTOP_SIDEBAR_MAX_WIDTH,
      sheetMaxWidth: DESKTOP_TAB_TOOLS_MAX_WIDTH
    }).sheetWidth;
  }, [desktopRightPanelOpen, desktopSidebarOpen, layoutViewportWidth, sidebarWidth]);

  useCadWorkspaceLayout({
    isDesktop,
    setLayoutMode: setViewerLayoutMode,
    setSidebarOpen,
    setTabToolsOpen,
    setLayoutViewportWidth,
    clampSidebarWidth,
    clampTabToolsWidth,
    setSidebarWidth,
    setTabToolsWidth,
    panelResizeStateRef,
    tabToolsResizeStateRef,
    defaultSidebarWidth: DEFAULT_SIDEBAR_WIDTH,
    sidebarMinWidth: DESKTOP_SIDEBAR_MIN_WIDTH,
    tabToolsMinWidth: DESKTOP_TAB_TOOLS_MIN_WIDTH,
    endPanelResize,
    endTabToolsResize
  });

  useEffect(() => {
    if (!catalogHydrated || !catalogEntries.length) {
      return;
    }
    pruneFileSessionState(
      fileSessionNamespace,
      catalogEntries.map((entry) => fileKey(entry)),
      { onWriteError: handlePersistenceWriteError }
    );
  }, [catalogEntries, catalogHydrated, fileSessionNamespace, handlePersistenceWriteError]);

  useEffect(() => {
    setOpenTabs((current) => {
      const next = current.filter((tab) => entryMap.has(tab.key));
      return next.length === current.length ? current : next;
    });
  }, [entryMap]);

  const expandFileViewerTreeToEntry = useCallback((entry) => {
    const directoryId = sidebarDirectoryIdForEntry(entry);
    if (!directoryId) {
      return;
    }

    const ancestorIds = collectAncestorDirectoryIds(directoryId);
    if (!ancestorIds.length) {
      return;
    }

    setExpandedDirectoryIds((current) => {
      let changed = false;
      const next = new Set(current);

      for (const directoryId of ancestorIds) {
        if (!next.has(directoryId)) {
          next.add(directoryId);
          changed = true;
        }
      }

      return changed ? next : current;
    });
  }, []);

  useEffect(() => {
    if (!catalogHydrated && !catalogEntries.length) {
      return;
    }
    setExpandedDirectoryIds((current) => {
      const next = new Set(current);
      const knownDirectoryIds = new Set(allDirectoryIds);
      let changed = false;

      for (const directoryId of current) {
        if (!knownDirectoryIds.has(directoryId)) {
          next.delete(directoryId);
          changed = true;
        }
      }

      return changed ? next : current;
    });
  }, [allDirectoryIds, catalogEntries.length, catalogHydrated]);

  useEffect(() => {
    if (
      initialFileViewerDirectoryStateRef.current.hasStoredState ||
      initialFileViewerDirectoryStateRef.current.initialRevealDone ||
      !selectedEntry
    ) {
      return;
    }

    initialFileViewerDirectoryStateRef.current.initialRevealDone = true;
    setFileViewerDirectoryStateInitialized(true);
    expandFileViewerTreeToEntry(selectedEntry);
  }, [expandFileViewerTreeToEntry, selectedEntry]);

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
  const selectedStepParameterRuntime = useMemo(() => {
    if (
      !selectedStepModuleDefinition ||
      !stepModuleEnabled ||
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
    stepModuleEnabled,
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
  const selectedStepPartRootActive = !isAssemblyView && selectedPartIds.includes(STEP_MODEL_ROOT_ID);
  const plainStepReferencePickingEnabled =
    effectiveRenderFormat === RENDER_FORMAT.STEP &&
    selectedEntryHasReferences &&
    !isAssemblyView;
  const topologyCapabilityRequested = Boolean(
    selectedEntry && requestedTopologyFileRef === fileKey(selectedEntry)
  );
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
    if (stepInteractionBlocked || stepModuleTreeSelectionDisabled) {
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
    stepInteractionBlocked,
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
  const measureModeActive = effectiveSupportsMeasure &&
    tabToolMode === TAB_TOOL_MODE.MEASURE &&
    Boolean(selectedMeshData) &&
    !stepInteractionBlocked &&
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
  }, [selectedKey, selectedEntry?.hash]);
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

  const measureToolDisabled = viewerLoading || !selectedMeshData;
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
    if (stepInteractionBlocked || stepModuleTreeSelectionDisabled) {
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
      setSidebarOpen(false);
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
      await copyTextToClipboard(
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
    if (stepInteractionBlocked || stepModuleTreeSelectionDisabled) {
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
      setSidebarOpen(false);
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
    stepInteractionBlocked,
    stepModuleTreeSelectionDisabled,
  ]);

  const selectStepTreeNode = useCallback((nodeId, { multiSelect = false } = {}) => {
    const normalizedNodeId = String(nodeId || "").trim();
    togglePartSelection(normalizedNodeId, { multiSelect, source: "tree" });
  }, [
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

  const handleModelReferenceActivate = useCallback((referenceId, { multiSelect = false } = {}) => {
    if (stepInteractionBlocked || stepModuleTreeSelectionDisabled) {
      return;
    }
    // A newer gesture supersedes any click waiting for selector topology. If
    // this gesture also needs topology, its exact file/tree/id replaces it below.
    pendingModelReferenceActivationRef.current = null;
    const nextReferenceId = String(referenceId || "").trim();
    const topologyReference = effectiveActiveReferenceMap.get(nextReferenceId) || null;
    const deferForTopology = Boolean(
      selectedEntry &&
      selectedEntryHasReferences &&
      effectiveRenderFormat === RENDER_FORMAT.STEP &&
      !selectedReferencesMatch
    );
    const decision = modelReferenceActivationDecision(nextReferenceId, {
      topologyReference,
      assemblyMode: viewerInAssemblyMode,
      resolvePartId: resolvePickedAssemblyPartId,
      deferForTopology,
      referenceKnown: effectiveActiveReferenceMap.has(nextReferenceId)
    });
    if (decision.kind === "clear") {
      clearAssemblySelection();
      return;
    }
    if (decision.kind === "reference") {
      toggleReferenceSelection(decision.referenceId, { multiSelect });
      return;
    }
    if (decision.kind === "part") {
      togglePartSelection(decision.partId, {
        multiSelect,
        renderPartId: decision.renderPartId
      });
      return;
    }
    if (decision.kind === "defer") {
      pendingModelReferenceActivationRef.current = nextReferenceId
        ? { fileRef: fileKey(selectedEntry), tree: selectedEntry.hash, referenceId: nextReferenceId, multiSelect }
        : null;
      setRequestedTopologyFileRef(fileKey(selectedEntry));
    }
  }, [
    clearAssemblySelection,
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

  // A click that first demands topology is not discarded. Once the selector
  // runtime for that exact artifact is ready, replay the same activation so
  // the first click selects the intended face/edge/part.
  useEffect(() => {
    const pending = pendingModelReferenceActivationRef.current;
    if (!pending) return;
    if (!pendingReferenceActivationMatches(pending, {
      fileRef: fileKey(selectedEntry),
      tree: selectedEntry?.hash
    })) {
      pendingModelReferenceActivationRef.current = null;
      return;
    }
    if (!selectedReferencesMatch) {
      return;
    }
    pendingModelReferenceActivationRef.current = null;
    handleModelReferenceActivate(pending.referenceId, { multiSelect: pending.multiSelect });
  }, [handleModelReferenceActivate, selectedEntry, selectedReferencesMatch]);

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
      await copyTextToClipboard(copyText);
      setCopyStatus("Copied reference");
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "Failed to copy reference");
    }
  }, [retainedPreviousStepMeshError, stepInteractionBlocked]);

  const copyStepTreeContextMenuReference = useCallback(async (id, { topology = false } = {}) => {
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
      await copyTextToClipboard(copyText);
      setCopyStatus("Copied reference");
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "Failed to copy reference");
    }
  }, [
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
    const entry = key ? entryMap.get(key) : null;
    if (entry) {
      writeCadParam(cadFileParamForEntry(entry), { history: "push" });
    }
    activateEntryTab(key);
    if (!isDesktop) {
      setSidebarOpen(false);
    }
  }, [activateEntryTab, entryMap, isDesktop, writeCadParam]);

  const handleRevealEntryInExplorerView = useCallback((entry) => {
    const targetKey = fileKey(entry);
    if (!targetKey || !entryMap.has(targetKey)) {
      return;
    }

    setQuery("");
    setFileViewerDirectoryStateInitialized(true);
    expandFileViewerTreeToEntry(entry);
    if (targetKey !== selectedKey) {
      writeCadParam(cadFileParamForEntry(entry), { history: "push" });
      activateEntryTab(targetKey);
    }
    handleSidebarOpenChange(true);
  }, [
    activateEntryTab,
    entryMap,
    expandFileViewerTreeToEntry,
    handleSidebarOpenChange,
    selectedKey,
    writeCadParam
  ]);

  const handleSelectTabToolMode = useCallback((mode) => {
    setViewerAlertOpen(false);
    // Anything unrecognized falls back to selection rather than sticking the
    // viewer in a mode with no tool behind it.
    const normalizedMode = mode === TAB_TOOL_MODE.DRAW || mode === TAB_TOOL_MODE.MEASURE || mode === TAB_TOOL_MODE.PAN
      ? mode
      : TAB_TOOL_MODE.REFERENCES;
    setTabToolMode(normalizedMode);
    if (
      selectedEntry &&
      selectedEntryHasReferences &&
      (normalizedMode === TAB_TOOL_MODE.REFERENCES || normalizedMode === TAB_TOOL_MODE.MEASURE)
    ) {
      setRequestedTopologyFileRef(fileKey(selectedEntry));
    }
    if (normalizedMode === TAB_TOOL_MODE.DRAW && drawingTool === DRAWING_TOOL.SURFACE_LINE) {
      setDrawingTool(DRAWING_TOOL.FREEHAND);
    }
  }, [drawingTool, selectedEntry, selectedEntryHasReferences]);

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
    setRequestedTopologyFileRef(fileKey(selectedEntry));
  }, [selectedEntry, selectedEntryHasReferences]);

  const handleToggleFileSheet = useCallback(() => {
    if (!selectedFileSheetKind) {
      return;
    }
    setViewerAlertOpen(false);
    setTabToolsOpen((current) => {
      const nextOpen = !current;
      if (nextOpen && !isDesktop) {
        setSidebarOpen(false);
      }
      return nextOpen;
    });
  }, [isDesktop, selectedFileSheetKind, setTabToolsOpen]);

  const handleCopyFileAssetReference = useCallback(async (entry, asset = "output", assetInfo = null, referenceKind = "path") => {
    const fileRef = entry ? fileKey(entry) : "";
    const assetKind = String(asset || "output").trim() || "output";
    const kind = String(referenceKind || "").trim();
    if (!fileRef) {
      return;
    }

    setCopyStatus("");
    setScreenshotStatus("");

    try {
      let copyText = "";
      let statusLabel = "Copied file reference";
      // The context menu builds its asset descriptors without viewerServerInfo (it has
      // none), so a catalog entry's ABSOLUTE `file` arrives un-rebased. Recompute the
      // descriptor here, where the server info lives, so the copied path and relative
      // path are the served root's, not the absolute path with its slash shaved off.
      const resolvedAsset = fileAccessAssetsForEntry(entry, { viewerServerInfo })[assetKind] || assetInfo;
      const targets = copyTargetsForFileAccessAsset(resolvedAsset, viewerServerInfo);
      if (kind === "filename") {
        copyText = targets.filename;
        statusLabel = "Copied filename";
      } else if (kind === "relativePath") {
        copyText = targets.relativePath;
        statusLabel = "Copied relative path";
      } else if (kind === "link") {
        // The link's origin is the one in the user's address bar — the URL they can
        // actually paste — with the server's self-reported URL standing in only when
        // there is no window to read it from.
        const origin = (typeof window !== "undefined" && window.location?.origin) ||
          String(viewerServerInfo?.url || "").trim();
        copyText = viewerDeepLinkForFileAccessAsset(resolvedAsset, viewerServerInfo, { origin });
        statusLabel = "Copied link";
      } else {
        copyText = targets.path;
        statusLabel = "Copied path";
      }

      if (!copyText) {
        throw new Error("No file reference is available to copy");
      }

      await copyTextToClipboard(copyText);
      const filename = String(resolvedAsset?.filename || "").trim();
      // Naming the file after "Copied filename" would just repeat what was copied.
      setCopyStatus(filename && copyText !== filename ? `${statusLabel} for ${filename}` : statusLabel);
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "Failed to copy file reference");
    }
  }, [viewerServerInfo]);

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
    copyStatus,
    screenshotStatus,
    setCopyStatus,
    setScreenshotStatus,
    previewMode,
    inspectionEnabled: !renderSession.enabled,
    viewerAlertOpen,
    tabToolsOpen,
    isDesktop,
    sidebarOpen,
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
    setSidebarOpen,
    setTabToolMode
  });

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
      sidebarOpen,
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
    setSidebarOpen(false);
    setTabToolsOpen(false);
    setPreviewMode(true);
  }, [
    previewMode,
    sidebarOpen,
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
      setSidebarOpen(previousUiState.sidebarOpen);
      setTabToolsOpen(previousUiState.tabToolsOpen);
      setTabToolMode(previousUiState.tabToolMode);
    }
  }, [
    previewMode,
    setSidebarOpen,
    setTabToolMode,
    setTabToolsOpen,
    setViewerAlertOpen
  ]);

  const toggleDirectory = (directoryId) => {
    setFileViewerDirectoryStateInitialized(true);
    setExpandedDirectoryIds((current) => {
      const next = new Set(current);
      if (next.has(directoryId)) {
        next.delete(directoryId);
      } else {
        next.add(directoryId);
      }
      return next;
    });
  };
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
  const fileSheetOpen = !!selectedFileSheetKind && selectedFileSheetHasSections && tabToolsOpen && !previewMode;
  const activeSidebarWidth = desktopSidebarOpen
    ? resolvedDesktopPanelWidths.sidebarWidth
    : 0;
  const activeSheetWidth = desktopRightPanelOpen
    ? resolvedDesktopPanelWidths.sheetWidth
    : 0;
  const sidebarShellWidth = isDesktop && desktopSidebarOpen
    ? activeSidebarWidth
    : isDesktop
      ? resolveDesktopPanelWidths({
        viewportWidth: layoutViewportWidth,
        sidebarOpen: true,
        sheetOpen: false,
        sidebarWidth,
        sheetWidth: 0,
        sidebarMinWidth: DESKTOP_SIDEBAR_MIN_WIDTH,
        sheetMinWidth: DESKTOP_TAB_TOOLS_MIN_WIDTH,
        sidebarMaxWidth: DESKTOP_SIDEBAR_MAX_WIDTH,
        sheetMaxWidth: DESKTOP_TAB_TOOLS_MAX_WIDTH
      }).sidebarWidth
    : DEFAULT_SIDEBAR_WIDTH;
  const viewportFrameInsets = {
    top: previewMode ? 0 : CAD_WORKSPACE_TOP_BAR_HEIGHT,
    right: activeSheetWidth,
    bottom: 0,
    left: activeSidebarWidth
  };
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
  const materialPickingEnabled = renderSession.enabled && selectedFileSheetKind === "step" && effectiveFileSheetOpenSectionIds.includes(FILE_SHEET_SECTION_IDS.MATERIALS);
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
    <SidebarProvider
      open={effectiveSidebarOpen}
      onOpenChange={handleSidebarOpenChange}
      mobileOpen={effectiveSidebarOpen}
      onMobileOpenChange={handleSidebarOpenChange}
      style={{ "--sidebar-width": `${sidebarShellWidth}px` }}
      className="relative h-svh overflow-hidden bg-transparent"
    >
      <div
        className="fixed inset-0 z-0"
        data-cad-scene-backdrop={sceneBackdrop}
        style={{ backgroundColor: sceneBackdrop }}
      >
        <CadRenderPane
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
          viewportFrameInsets={viewportFrameInsets}
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
          viewPlaneOffsetRight={viewportFrameInsets.right + 16}
          viewerMode={robotComponentsActive ? "assembly" : viewerMode}
          robotComponentPicking={robotComponentsActive}
          assemblyPickingActive={robotComponentsActive || viewerInAssemblyMode}
          assemblyParts={robotComponentsActive ? (selectedUrdfPreview.meshData?.parts || EMPTY_LIST) : viewerAssemblyRenderParts}
          hiddenPartIds={viewerHiddenPartIds}
          selectedPartIds={robotComponentsActive ? robotSelection.selectedIds : viewerSelectedPartIds}
          hoveredPartId={robotComponentsActive ? robotSelection.hoveredId : viewerHoveredPartIds}
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
          handleModelHoverChange={robotComponentsActive ? robotSelection.hover : handleModelHoverChange}
          handleModelReferenceActivate={robotComponentsActive ? selectRobotComponent : handleModelReferenceActivate}
          handleModelReferenceDoubleActivate={robotComponentsActive ? undefined : handleModelReferenceDoubleActivate}
          handleModelReferenceContext={robotComponentsActive ? undefined : handleModelReferenceContext}
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
          handleScreenshotCopy={handleScreenshotCopy}
        />
      </div>

      <SidebarInset className="pointer-events-none relative z-10 h-svh min-w-0 overflow-hidden bg-transparent">
        <CadWorkspaceTopBar
          previewMode={previewMode}
          fileStatus={fileStatus}
          onFileStatusClick={fileStatusAlert ? () => setViewerAlertOpen(true) : undefined}
          renderMode={renderSession.enabled}
          onRenderModeChange={handleRenderEnabledChange}
          sidebarLabelForEntry={sidebarLabelForEntry}
          directoryTree={allEntriesTree}
          selectedKey={selectedKey}
          selectedEntry={selectedEntry}
          onSelectEntry={handleSelectEntry}
          entrySourceFormat={entrySourceFormat}
          entryHasMesh={entryHasMesh}
          entryHasDxf={entryHasDxf}
          entryHasUrdf={entryHasUrdf}
          activeStepArtifactGenerationFile={activeStepArtifactGenerationFiles}
              loadingFiles={viewerLoadingFiles}
          stepArtifactGenerationAvailable={stepArtifactGenerationAvailable}
          selectedStepSourceStatus={selectedStepSourceStatus}
          canCopyFileAssetPaths={filePathCopyAvailable}
          onRevealInExplorerView={handleRevealEntryInExplorerView}
          onCopyFileAssetReference={handleCopyFileAssetReference}
          fileSheetKind={selectedFileSheetHasSections ? selectedFileSheetKind : ""}
          fileSheetOpen={fileSheetOpen}
          onToggleFileSheet={handleToggleFileSheet}
          colorSchemePreference={colorSchemePreference}
          resolvedColorSchemeMode={resolvedColorSchemeMode}
          onColorSchemePreferenceChange={handleColorSchemePreferenceChange}
        />

        <div className="pointer-events-none relative min-h-0 flex-1 overflow-hidden">
          <div className="flex h-full min-w-0">
            <FileViewerSidebar
              previewMode={previewMode}
              query={query}
              onQueryChange={setQuery}
              filteredEntries={filteredEntries}
              catalogEntries={catalogEntries}
              filteredEntriesTree={filteredEntriesTree}
              selectedKey={selectedKey}
              expandedDirectoryIds={expandedDirectoryIds}
              onToggleDirectory={toggleDirectory}
              onSelectEntry={handleSelectEntry}
              entrySourceFormat={entrySourceFormat}
              entryHasMesh={entryHasMesh}
              entryHasDxf={entryHasDxf}
              entryHasUrdf={entryHasUrdf}
              activeStepArtifactGenerationFile={activeStepArtifactGenerationFiles}
              loadingFiles={viewerLoadingFiles}
              stepArtifactGenerationAvailable={stepArtifactGenerationAvailable}
              canCopyFileAssetPaths={filePathCopyAvailable}
              onRevealInExplorerView={handleRevealEntryInExplorerView}
              onCopyFileAssetReference={handleCopyFileAssetReference}
              catalogHydrated={catalogHydrated}
              catalogRefreshing={catalogRefreshing}
              catalogError={catalogError}
              resizable={isDesktop}
              onStartResize={handleStartSidebarResize}
            />

            <div className="pointer-events-none relative min-w-0 flex-1 overflow-hidden">
              <FloatingToolBar
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
              />

              {!previewMode && !viewerAlert && !selectedEntry && !missingFileRef && !fileParamSelectionPending ? (
                <CadWorkspaceHome
                  entries={catalogEntries}
                  onSelectEntry={handleSelectEntry}
                  catalogHydrated={catalogHydrated}
                  catalogRefreshing={catalogRefreshing}
                  catalogError={catalogError}
                />
              ) : null}

              <ViewerLoadingOverlay
                loading={presentationState?.file === selectedKey && presentationState?.covering ? null : loading}
                previewMode={previewMode}
                operationKey={selectedKey || explicitFileParam}
              />
            </div>

            {selectedFileSheetKind === "step" ? (
              <StepFileSheet
                key={`step:${selectedKey}`}
                open={fileSheetOpen}
                isDesktop={isDesktop}
                width={activeSheetWidth || tabToolsWidth}
                onOpenChange={setTabToolsOpen}
                onStartResize={handleStartFileSheetResize}
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
                isDesktop={isDesktop}
                width={activeSheetWidth || tabToolsWidth}
                selectedEntry={selectedEntry}
                onOpenChange={setTabToolsOpen}
                onStartResize={handleStartFileSheetResize}
                joints={movableUrdfJoints}
                components={selectedUrdfComponents}
                componentSelection={{ ...robotSelection, select: selectRobotComponent }}
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
                isDesktop={isDesktop}
                width={activeSheetWidth || tabToolsWidth}
                selectedEntry={selectedEntry}
                onOpenChange={setTabToolsOpen}
                onStartResize={handleStartFileSheetResize}
                viewerServerInfo={viewerServerInfo}
                suppressDynamicMetadataStatus={selectedArtifactGenerating}
                renderMode={renderSession.enabled}
                settingsTabs={renderSession.enabled ? settingsTabs : [
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
                isDesktop={isDesktop}
                width={activeSheetWidth || tabToolsWidth}
                selectedEntry={selectedEntry}
                onOpenChange={setTabToolsOpen}
                onStartResize={handleStartFileSheetResize}
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
          viewerAlert={fileStatusAlert}
          previewMode={previewMode}
          setViewerAlertOpen={setViewerAlertOpen}
        />
      </SidebarInset>
    </SidebarProvider>
  );
}

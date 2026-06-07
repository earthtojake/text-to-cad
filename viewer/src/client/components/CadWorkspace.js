"use client";

import { startTransition, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeftRight, ArrowRight, Circle, Eraser, Minus, PaintBucket, PenTool, Square } from "lucide-react";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import CadRenderPane from "./workbench/CadRenderPane";
import DxfFileSheet from "./workbench/DxfFileSheet";
import GcodeFileSheet from "./workbench/GcodeFileSheet";
import FileViewerSidebar from "./workbench/FileViewerSidebar";
import {
  DisplaySettingsSection,
  ThemeSettingsSections
} from "./workbench/ThemeSettingsPopover";
import MeshFileSheet from "./workbench/MeshFileSheet";
import ImplicitFileSheet from "./workbench/ImplicitFileSheet";
import StepFileSheet, { STEP_TREE_ROOT_ITEM_LIMIT } from "./workbench/StepFileSheet";
import StatusToast from "./workbench/StatusToast";
import UrdfFileSheet from "./workbench/UrdfFileSheet";
import ViewerAlertDialog from "./workbench/ViewerAlertDialog";
import ViewerLoadingOverlay from "./workbench/ViewerLoadingOverlay";
import FloatingToolBar from "./workbench/FloatingToolBar";
import CadWorkspaceTopBar from "./workbench/CadWorkspaceTopBar";
import CadWorkspaceHome from "./workbench/CadWorkspaceHome";
import { useCadAssets } from "./workbench/hooks/useCadAssets";
import {
  resolveDesktopPanelWidths,
  useCadWorkspaceLayout
} from "./workbench/hooks/useCadWorkspaceLayout";
import { useCadWorkspaceSelection } from "./workbench/hooks/useCadWorkspaceSelection";
import { useCadDirectorySession } from "./workbench/hooks/useCadDirectorySession";
import { useCadWorkspaceSelectors } from "./workbench/hooks/useCadWorkspaceSelectors";
import { useCadWorkspaceShortcuts } from "./workbench/hooks/useCadWorkspaceShortcuts";
import {
  applyColorSchemeToDocument,
  DARK_COLOR_SCHEME_ID,
  normalizeColorSchemeId,
  readColorSchemePreference,
  resolveColorSchemeMode,
  writeColorSchemePreference
} from "@/ui/colorScheme";
import {
  inferThemeSettingsSceneTone,
  normalizeThemeSettings,
  resolveThemeSettingsDisplayEdgeSettings,
  resolveThemeSettingsForColorMode,
  THEME_COLOR_MODES
} from "cadjs/lib/themeSettings";
import {
  displayModeForcesEdges,
  displayModeIsWireframe,
  normalizeDisplaySettings
} from "cadjs/lib/displaySettings";
import { clonePerspectiveSnapshot } from "cadjs/lib/perspective";
import {
  ASSET_STATUS,
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
import {
  entrySourceFormat,
  fileSheetKindForEntry,
  isRobotRenderFormat
} from "cadjs/lib/fileFormats";
import {
  buildViewerDxfAlert,
  buildViewerImplicitAlert,
  buildViewerMeshAlert
} from "@/workbench/viewerAlerts";
import {
  buildAssemblyMateCopyText,
  buildNormalizedReferenceState,
  buildReferenceCacheKey,
  buildSelectionCopyButtonLabel,
  buildSelectionCopyPayload,
  buildWholeStepEntryCopyReference,
  cadRefQueryHasKnownEntry,
  canonicalCadRefCopyText,
  collectCadRefSelectionRequest,
  computeNextSelectionIds,
  orderedStringListEqual,
  parseAssemblyPartReferenceSelectionId,
  resolveCadRefSelection,
  uniqueStringList
} from "@/workbench/referenceSelection";
import {
  entryAssetHash,
  entryAssetUrl,
  entryHasDisplayEdges,
  entryHasDxf,
  entryHasGcode,
  entryHasMesh,
  entryHasReferences,
  entryHasUrdf,
  entryMeshAssetSignature,
  entryStepModuleUrl,
  entryUrdfAssetHash
} from "cadjs/lib/entryAssets";
import {
  hasStepGlbByteCost,
  isLargeMeshData,
  isLargeStepGlbEntry
} from "cadjs/lib/render/meshCost";
import {
  buildAvailableThemePresets,
  cadWorkspaceDefaultFileSheetWidthForViewport,
  createDirectorySessionThemeSlice,
  cloneDrawingStrokes,
  cloneTabSnapshot,
  createTabRecord,
  deleteCustomThemePreset,
  drawingStrokesEqual,
  getAvailableThemePresetIdForSettings,
  readCadDirectorySessionState,
  readCustomThemePresets,
  readThemeSettingsState,
  readThemeSettingsStateFromAppearanceQuery,
  readDirectoryThemeSettingsState,
  resetThemePresetToDefault,
  restoreDefaultThemePresets,
  saveAndActivateCustomThemePreset,
  updateThemePresetSettings,
  writeCadDirectorySessionState,
  writeCustomThemePresets,
  writeThemeSettings,
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
  CAD_DIRECTORY_STORAGE_EVENT_ACTION,
  cadDirectoryStorageEventAction
} from "@/workbench/storageEvents";
import {
  clampNumber,
  shallowObjectValuesEqual,
  toFiniteNumber
} from "@/workbench/valueUtils";
import {
  animationNowMs,
  buildDefaultStepModuleAnimationState,
  findStepModuleAnimation
} from "@/workbench/stepModuleAnimation";
import {
  getStepAnimationElapsed,
  getStepAnimationParameterValues,
  resetStepAnimationStore,
  setStepAnimationElapsed,
  setStepAnimationFrame
} from "@/workbench/stepAnimationStore";
import {
  buildDefaultParameterAnimationState,
  findParameterAnimation
} from "@/workbench/parameterAnimation";
import {
  buildUrdfJointAnglesCopyText,
  cloneJointValueMap,
  emptyUrdfPosePickerState,
  interpolateTrajectoryJointValues,
  jointValueSubsetClose,
  normalizePoint3,
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
  readCadDirParam,
  readCadParam,
  readCadRefQueryParams,
  readNavigationCadRefQueryParams,
  selectedEntryKeyFromUrl,
  sidebarDirectoryIdForEntry,
  sidebarLabelForEntry,
  shouldDeferFileParamSelection,
  writeCadDirParam,
  writeCadParam,
  writeCadRefQueryParams,
} from "@/workbench/sidebar";
import { buildCadRefToken } from "cadjs/lib/cadRefs.js";
import {
  buildDxfPreviewMeshData,
  extractOrderedDxfBendLines,
  normalizeDxfBendAngleDeg,
  normalizeDxfBendDirection,
  normalizeDxfBendSettings,
  DEFAULT_DXF_PREVIEW_THICKNESS_MM,
  normalizeDxfPreviewThicknessMm
} from "cadjs/lib/dxf/buildPreviewMesh";
import {
  buildGcodePreviewMeshData,
  DEFAULT_GCODE_PREVIEW_DETAIL_LEVEL,
  normalizeGcodePreviewOptions
} from "cadjs/lib/gcode/buildPreviewMesh";
import {
  applyUrdfPoseToMeshData,
  buildDefaultUrdfJointValues,
  buildUrdfMeshGeometry,
  clampJointValueDeg,
  linkOriginInFrame,
  rootPointInFrame
} from "cadjs/lib/urdf/kinematics";
import {
  jointValuesByNameToNative,
  measureUrdfMotionResult,
  normalizeMotionTargetPosition,
  validateUrdfMotionTrajectory,
  validateUrdfMotionJointValues
} from "cadjs/lib/urdf/motion";
import { checkMoveIt2ServerLive, moveit2ServerEnabled, requestMoveIt2Server } from "cadjs/lib/urdf/moveit2ServerClient";
import {
  cadViewerUsesHostedCatalog,
  readActiveCadDir,
  refreshCadCatalog,
  refreshCadGenerationStatus,
  requestStepArtifactGeneration,
  requestStepSourceStatus
} from "../workbench/cadManifestStore.js";
import {
  STEP_ARTIFACT_GENERATION_FAILURE_DISPLAY_THRESHOLD,
  runStepArtifactGenerationWithRetries,
  stepArtifactCanGenerate,
  stepArtifactGenerationFailureCount,
  stepArtifactGenerationInProgress,
  validateGeneratedStepArtifactPayload
} from "@/workbench/stepArtifactStatus";
import {
  buildFileStatusItems,
  fileStatusHasWarningsOrErrors,
  mostIntenseFileStatusLevel
} from "@/workbench/fileStatusItems";
import {
  rootAssemblyInspectionNodeId,
  selectableAssemblyNodeIdsForInspection,
  buildAssemblyLeafToNodePickMap,
  descendantLeafPartIds,
  findAssemblyNode,
  flattenAssemblyNodes,
  flattenAssemblyLeafParts,
  leafPartIdsForAssemblySelection,
  resolveAssemblyPickedPartId
} from "cadjs/lib/assembly/meshData";
import {
  assemblyNodeContainsNode,
  assemblyPathToNode,
  minimalAssemblyIsolationNodeIds,
  selectableTreeNodeIdsForIsolation
} from "@/workbench/assemblyIsolation";
import {
  assignStepTreeTopologyReferencePartIds,
  buildStepTreeRoot,
  buildStepTreeRootWithTopology,
  collectStepTreeAncestorIds,
  STEP_MODEL_ROOT_ID,
  STEP_MODEL_RENDER_PART_ID,
  STEP_TREE_TOPOLOGY_NODE_PREFIX,
  stepTreeRootChildIndexForNode,
  stepTreeNodeChildren
} from "cadjs/lib/step/stepTree";
import {
  loadStepModuleDefinition,
  normalizeStepModuleParameterValues
} from "cadjs/common/stepModule";
import {
  normalizeParameterValue,
  normalizeParameterValues
} from "implicitjs/common/parameters.js";
import { copyTextToClipboard, readTextFromClipboard } from "@/ui/clipboard";
import { triggerUrlDownload } from "@/ui/download";
import {
  copyTargetsForFileAccessAsset,
  downloadUrlForFileAsset,
  openUrlForFileAsset
} from "@/workbench/fileAccessAssets";
import {
  buildStepModuleParamsCopyText,
  parseStepModuleParamsPasteText
} from "@/workbench/stepModuleParameterControls";
import {
  buildParameterValuesCopyText,
  parseParameterValuesPasteText
} from "@/workbench/parameterControls";
import {
  normalizeImplicitGraphicsSettings
} from "@/workbench/implicitGraphicsSettings";
import {
  DEFAULT_IMPLICIT_EXPORT_RESOLUTION,
  requestImplicitCadExport
} from "@/workbench/implicitExport";

const DEFAULT_DOCUMENT_TITLE = "CAD Viewer";
const LOCAL_ASSET_BACKEND = "local-fs";
const EMPTY_LIST = Object.freeze([]);
const MOVEIT2_SERVER_ENABLED = moveit2ServerEnabled();
const URDF_POSE_PICKER_DEFAULT_CENTER = Object.freeze([0, 0, 0]);
const DESKTOP_SIDEBAR_MIN_WIDTH = 150;
const DESKTOP_SIDEBAR_MAX_WIDTH = 520;
const DEFAULT_SIDEBAR_WIDTH = CAD_WORKSPACE_DEFAULT_SIDEBAR_WIDTH;
const DESKTOP_TAB_TOOLS_MIN_WIDTH = 240;
const DESKTOP_TAB_TOOLS_MAX_WIDTH = 448;
const DEFAULT_TAB_TOOLS_WIDTH = CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH;
const CAD_WORKSPACE_TOP_BAR_HEIGHT = 44;
const IMPLICIT_PARAMETER_RENDER_THROTTLE_MS = 36;
const IMPLICIT_PARAMETER_ANIMATION_TICK_MS = 80;
const IMPLICIT_DYNAMIC_RENDER_SETTLE_MS = 220;
const DEFAULT_LARGE_FILE_STATE = Object.freeze({
  selectableTopologyEnabled: false
});

function viewerAssetBackendFromEnv() {
  return String(import.meta.env?.VIEWER_ASSET_BACKEND || LOCAL_ASSET_BACKEND).trim().toLowerCase();
}

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

function readViewerPrefersDark() {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches === true;
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

const NATIVE_CAD_SELECTOR_RE = /^(?:o\d+(?:\.\d+)*(?:\.[sfev]\d+)?|[sfev]\d+|m\d+)$/i;

function nativeCadSelectorCandidate(value) {
  const selector = String(value || "").trim();
  return NATIVE_CAD_SELECTOR_RE.test(selector) ? selector : "";
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
    selectedMateIds = [],
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
    ...selectedCopyLinesFromIds(selectedPartIds, copyReferenceMap),
    ...selectedCopyLinesFromIds(selectedMateIds, copyReferenceMap)
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

function expandableStepTreeNodeIdsForWorkspace(root, { omitRoot = false } = {}) {
  if (!root) {
    return [];
  }
  const ids = [];
  const stack = [root];
  while (stack.length) {
    const node = stack.pop();
    const nodeId = stepTreeNodeIdForWorkspace(node);
    const children = stepTreeNodeChildren(node);
    if ((!omitRoot || node !== root) && nodeId && children.length) {
      ids.push(nodeId);
    }
    for (let index = children.length - 1; index >= 0; index -= 1) {
      stack.push(children[index]);
    }
  }
  return ids;
}

function buildStepTreeExpansionMenuState({
  root,
  isAssemblyView = false,
  expandedTreeNodeIds = [],
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
    .filter((row) => stepTreeNodeChildren(row).length && !expandedTreeNodeIdSet.has(stepTreeNodeIdForWorkspace(row)))
    .map((row) => stepTreeNodeIdForWorkspace(row))
    .filter(Boolean);
  const expandedActionNodeIds = actionRows
    .filter((row) => stepTreeNodeChildren(row).length && expandedTreeNodeIdSet.has(stepTreeNodeIdForWorkspace(row)))
    .map((row) => stepTreeNodeIdForWorkspace(row))
    .filter(Boolean);
  const expandableTreeNodeIds = expandableStepTreeNodeIdsForWorkspace(root, {
    omitRoot: stepTreeRootRowIsElidedForWorkspace(root, isAssemblyView)
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

function focusedAssemblyInteractionNodeId(root, nodeIds) {
  if (!root || !Array.isArray(nodeIds) || !nodeIds.length) {
    return "";
  }
  let bestNodeId = "";
  let bestDepth = -1;
  for (const nodeId of nodeIds) {
    const normalizedNodeId = String(nodeId || "").trim();
    if (!normalizedNodeId) {
      continue;
    }
    const path = assemblyPathToNode(root, normalizedNodeId);
    const node = path[path.length - 1] || null;
    if (String(node?.nodeType || "").trim() !== "assembly") {
      continue;
    }
    const children = Array.isArray(node?.children) ? node.children : [];
    if (!children.length || path.length <= bestDepth) {
      continue;
    }
    bestNodeId = normalizedNodeId;
    bestDepth = path.length;
  }
  return bestNodeId;
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
    if (childType.startsWith("topology-") && childId && children.length) {
      expansionIds.push(childId);
    }
    for (let index = children.length - 1; index >= 0; index -= 1) {
      stack.push(children[index]);
    }
  }
  return expansionIds;
}

function collectStepTreeRevealExpansionIds(root, nodeId, { expandSelf = false } = {}) {
  const normalizedNodeId = String(nodeId || "").trim();
  if (!root || !normalizedNodeId) {
    return [];
  }
  const node = findStepTreeNodeForWorkspace(root, normalizedNodeId);
  const expansionIds = collectStepTreeAncestorIds(root, normalizedNodeId);
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

function buildStepModuleAnimationFrameValues({
  definition,
  animation,
  elapsedSec,
  speed,
  parameterValues
}) {
  if (!definition) {
    return {};
  }
  const baseValues = normalizeStepModuleParameterValues(definition, parameterValues);
  if (typeof animation?.update !== "function") {
    return baseValues;
  }
  const duration = Math.max(Number(animation.duration) || 1, 0.001);
  const safeElapsedSec = clampNumber(elapsedSec, 0, duration);
  const progress = duration > 0 ? clampNumber(safeElapsedSec / duration, 0, 1) : 0;
  const nextValues = { ...baseValues };
  const set = (parameterId, value) => {
    const id = String(parameterId || "").trim();
    const parameter = definition.parameterMap?.[id];
    if (!parameter) {
      return;
    }
    nextValues[id] = normalizeParameterValue(parameter, value);
  };
  try {
    animation.update({
      elapsed: safeElapsedSec,
      elapsedSec: safeElapsedSec,
      duration,
      progress,
      cycle: duration > 0 ? safeElapsedSec / duration : 0,
      loop: animation.loop !== false,
      params: baseValues,
      set,
      speed: clampNumber(speed, 0.1, 5)
    });
  } catch (error) {
    console.error("STEP animation update failed", error);
  }
  return nextValues;
}

function useThrottledValue(value, intervalMs, resetKey = "") {
  const [throttledValue, setThrottledValue] = useState(value);
  const latestValueRef = useRef(value);
  const resetKeyRef = useRef(resetKey);
  const lastEmitTimeRef = useRef(0);
  const timerIdRef = useRef(0);

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
      setThrottledValue(value);
      return;
    }

    if (interval <= 0 || typeof window === "undefined") {
      lastEmitTimeRef.current = now;
      setThrottledValue(value);
      return;
    }

    const elapsed = now - lastEmitTimeRef.current;
    if (elapsed >= interval) {
      if (timerIdRef.current) {
        window.clearTimeout(timerIdRef.current);
        timerIdRef.current = 0;
      }
      lastEmitTimeRef.current = now;
      setThrottledValue(value);
      return;
    }

    if (!timerIdRef.current) {
      timerIdRef.current = window.setTimeout(() => {
        timerIdRef.current = 0;
        lastEmitTimeRef.current = typeof performance !== "undefined" && typeof performance.now === "function"
          ? performance.now()
          : Date.now();
        setThrottledValue(latestValueRef.current);
      }, interval - elapsed);
    }
  }, [intervalMs, resetKey, value]);

  return throttledValue;
}

function buildAnimatedImplicitParameterValues(definition, animation, currentValues, elapsedSec) {
  if (!definition || typeof animation?.update !== "function") {
    return currentValues;
  }
  const duration = Math.max(Number(animation.duration) || 1, 0.001);
  const clampedElapsedSec = clampNumber(elapsedSec, 0, duration);
  const progress = duration > 0 ? clampNumber(clampedElapsedSec / duration, 0, 1) : 0;
  const normalizedCurrent = normalizeParameterValues(definition, currentValues);
  const nextValues = { ...normalizedCurrent };
  const set = (parameterId, value) => {
    const id = String(parameterId || "").trim();
    const parameter = definition.parameterMap?.[id];
    if (!parameter) {
      return;
    }
    nextValues[id] = normalizeParameterValue(parameter, value);
  };
  animation.update({
    ...normalizedCurrent,
    elapsed: clampedElapsedSec,
    elapsedSec: clampedElapsedSec,
    duration,
    progress,
    cycle: duration > 0 ? clampedElapsedSec / duration : 0,
    t: clampedElapsedSec,
    loop: animation.loop !== false,
    params: normalizedCurrent,
    set
  });
  return nextValues;
}

async function readResponseError(response, fallback) {
  try {
    const payload = await response.json();
    const error = String(payload?.error || payload?.message || fallback).trim();
    return error || fallback;
  } catch {
    return fallback;
  }
}

function buildDxfCacheKey(entry) {
  const fileRef = fileKey(entry);
  const dxfHash = entryAssetHash(entry, "dxf");
  return fileRef && dxfHash ? `${fileRef}:${dxfHash}` : "";
}

function ownProperty(object, key) {
  return Object.prototype.hasOwnProperty.call(object || {}, key);
}

function entryHasImplicitAsset(entry) {
  return Boolean(entryAssetUrl(entry, "implicit") && entryAssetHash(entry, "implicit"));
}

function mergeStepSourceStatusIntoEntry(entry, stepSourceStatus) {
  if (!entry || !stepSourceStatus || typeof stepSourceStatus !== "object") {
    return entry;
  }
  const nextEntry = { ...entry };
  if (ownProperty(stepSourceStatus, "artifact")) {
    if (stepSourceStatus.artifact && typeof stepSourceStatus.artifact === "object") {
      nextEntry.artifact = stepSourceStatus.artifact;
    } else {
      delete nextEntry.artifact;
    }
  }

  const sourceKind = String(stepSourceStatus.sourceKind || "").trim().toLowerCase();
  if (sourceKind) {
    nextEntry.sourceKind = sourceKind;
  }
  const sourcePath = String(stepSourceStatus.sourcePath || "").trim();
  if (sourceKind === "python" && sourcePath) {
    nextEntry.source = {
      ...(entry.source && typeof entry.source === "object" ? entry.source : {}),
      file: sourcePath,
      sourcePath,
    };
  } else if (sourceKind === "step" && ownProperty(nextEntry, "source")) {
    delete nextEntry.source;
  }
  return nextEntry;
}

function normalizeViewerDirectoryOptions(viewerServerInfo) {
  const seen = new Set();
  const options = [];
  for (const option of Array.isArray(viewerServerInfo?.activeDirectories) ? viewerServerInfo.activeDirectories : []) {
    const dir = String(option?.dir || "").trim();
    const rootPath = String(option?.rootPath || "").trim();
    const key = rootPath || dir;
    if (!dir || !key || seen.has(key)) {
      continue;
    }
    seen.add(key);
    options.push({
      dir,
      rootPath,
      rootName: String(option?.rootName || "").trim()
    });
  }
  return options;
}

export default function CadWorkspace({
  manifestEntries: manifestEntriesProp = [],
  generationStatus = null,
  manifestRevision = 0,
  catalogHydrated = false,
  catalogRefreshing = false,
  catalogError = "",
  activeDir = ""
}) {
  const manifestEntries = Array.isArray(manifestEntriesProp) ? manifestEntriesProp : [];
  const catalogEntries = manifestEntries;
  const explicitDirParam = readCadDirParam();
  const explicitFileParam = readCadParam();
  const viewerAssetBackend = viewerAssetBackendFromEnv();
  const activeGeneratorFiles = useMemo(() => (
    Object.entries(generationStatus?.files || {})
      .filter(([, status]) => status?.running === true)
      .map(([file]) => String(file || "").trim())
      .filter(Boolean)
  ), [generationStatus]);
  const catalogRootDir = String(activeDir || "").trim();
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
  const viewerServerBackend = String(viewerServerInfo?.backend || "").trim().toLowerCase();
  const directoryCatalogActive = Boolean(catalogRootDir) ||
    cadViewerUsesHostedCatalog(viewerAssetBackend) ||
    cadViewerUsesHostedCatalog(viewerServerBackend);
  const [selectedKey, setSelectedKey] = useState("");
  const [fileSheetOpenSectionIds, setFileSheetOpenSectionIds] = useState(null);
  const [dxfThicknessMm, setDxfThicknessMm] = useState(0);
  const [dxfBendSettings, setDxfBendSettings] = useState([]);
  const [gcodeShowTravel, setGcodeShowTravel] = useState(false);
  const [gcodeMaxLayer, setGcodeMaxLayer] = useState(null);
  const [gcodeFullDetail, setGcodeFullDetail] = useState(false);
  const [gcodePreviewDetailLevel, setGcodePreviewDetailLevel] = useState(DEFAULT_GCODE_PREVIEW_DETAIL_LEVEL);
  const [referenceQuery, setReferenceQuery] = useState("");
  const [selectedReferenceIds, setSelectedReferenceIds] = useState([]);
  const [selectedMateIds, setSelectedMateIds] = useState([]);
  const [largeFileState, setLargeFileState] = useState(() => normalizeLargeFileState(DEFAULT_LARGE_FILE_STATE));
  const [hoveredListReferenceId, setHoveredListReferenceId] = useState("");
  const [hoveredModelReferenceId, setHoveredModelReferenceId] = useState("");
  const [hoveredMateId, setHoveredMateId] = useState("");
  const [selectedPartIds, setSelectedPartIds] = useState([]);
  const [selectedRenderPartIdByAssemblyPartId, setSelectedRenderPartIdByAssemblyPartId] = useState({});
  const [selectedWholeEntryCadRefToken, setSelectedWholeEntryCadRefToken] = useState("");
  const [expandedStepTreeNodeIds, setExpandedStepTreeNodeIds] = useState([]);
  const [activeTreeNodeScrollKey, setActiveTreeNodeScrollKey] = useState("");
  const [stepTreeRootShowMore, setStepTreeRootShowMore] = useState(false);
  const [hiddenPartIds, setHiddenPartIds] = useState([]);
  const [isolatedAssemblyNodeIds, setIsolatedAssemblyNodeIds] = useState([]);
  const [viewerContextMenu, setViewerContextMenu] = useState(null);
  const [displaySettings, setDisplaySettings] = useState(() => normalizeDisplaySettings());
  const [hoveredListPartId, setHoveredListPartId] = useState("");
  const [hoveredModelPartId, setHoveredModelPartId] = useState("");
  const [copyStatus, setCopyStatus] = useState("");
  const [stepUpdateInProgress, setStepUpdateInProgress] = useState(false);
  const [stepArtifactGenerationStateByKey, setStepArtifactGenerationStateByKey] = useState({});
  const [stepSourceStatusState, setStepSourceStatusState] = useState({
    key: "",
    file: "",
    status: null,
    loading: false,
    error: ""
  });
  const [screenshotStatus, setScreenshotStatus] = useState("");
  const [fileAccessBusyKey, setFileAccessBusyKey] = useState("");
  const [persistenceStatus, setPersistenceStatus] = useState("");
  const [motionErrorStatus, setMotionErrorStatus] = useState("");
  const [moveit2ServerLive, setMoveIt2ServerLive] = useState(false);
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
  const [customThemePresets, setCustomThemePresets] = useState(readCustomThemePresets);
  const [themeState, setThemeState] = useState(() => readDirectoryThemeSettingsState(readCustomThemePresets()));
  const themeSettings = themeState.settings;
  const themePresetId = themeState.presetId;
  const availableThemePresets = useMemo(() => buildAvailableThemePresets(customThemePresets), [customThemePresets]);
  const [systemPrefersDark, setSystemPrefersDark] = useState(readViewerPrefersDark);
  const [colorSchemePreference, setColorSchemePreference] = useState(readColorSchemePreference);
  const resolvedColorSchemeMode = useMemo(
    () => resolveColorSchemeMode(colorSchemePreference, { prefersDark: systemPrefersDark }),
    [colorSchemePreference, systemPrefersDark]
  );
  const resolvedThemeSettings = useMemo(
    () => resolveThemeSettingsForColorMode(themeSettings, {
      prefersDark: resolvedColorSchemeMode === DARK_COLOR_SCHEME_ID
    }),
    [resolvedColorSchemeMode, themeSettings]
  );
  const resolvedDisplayEdgeSettings = useMemo(
    () => resolveThemeSettingsDisplayEdgeSettings(resolvedThemeSettings),
    [resolvedThemeSettings]
  );
  const cadWorkspaceGlassTone = useMemo(() => inferThemeSettingsSceneTone(resolvedThemeSettings), [resolvedThemeSettings]);
  const updateDisplaySettings = useCallback((nextValue) => {
    setDisplaySettings((current) => normalizeDisplaySettings(
      typeof nextValue === "function" ? nextValue(current) : nextValue
    ));
  }, []);
  const updateImplicitGraphicsSettings = useCallback((nextValue) => {
    setImplicitGraphicsSettings((current) => normalizeImplicitGraphicsSettings(
      typeof nextValue === "function" ? nextValue(current) : nextValue
    ));
  }, []);
  const [previewMode, setPreviewMode] = useState(false);
  const [tabToolsWidth, setTabToolsWidth] = useState(readInitialFileSheetWidth);
  const [fileSheetWidthIsCustom, setFileSheetWidthIsCustom] = useState(readInitialFileSheetWidthIsCustom);
  const [drawingTool, setDrawingTool] = useState(DRAWING_TOOL.FREEHAND);
  const [viewerPerspective, setViewerPerspective] = useState(null);
  const [tabToolMode, setTabToolMode] = useState(TAB_TOOL_MODE.REFERENCES);
  const [drawingStrokes, setDrawingStrokes] = useState([]);
  const [drawingUndoStack, setDrawingUndoStack] = useState([]);
  const [drawingRedoStack, setDrawingRedoStack] = useState([]);
  const [jointValuesByFileRef, setJointValuesByFileRef] = useState({});
  const [urdfMotionStateByFileRef, setUrdfMotionStateByFileRef] = useState({});
  const [stepModuleLoadState, setStepModuleLoadState] = useState({
    url: "",
    status: "idle",
    error: "",
    definition: null
  });
  const [stepModuleParameterValues, setStepModuleParameterValues] = useState({});
  const [stepModuleEnabled, setStepModuleEnabled] = useState(true);
  const [stepModuleAnimationState, setStepModuleAnimationState] = useState({
    activeId: "",
    playing: false,
    elapsedSec: 0,
    speed: 1
  });
  const stepModuleParameterValuesRef = useRef(stepModuleParameterValues);
  const stepModuleAnimationStateRef = useRef(stepModuleAnimationState);
  const [implicitParameterValues, setImplicitParameterValues] = useState({});
  const [implicitAnimationState, setImplicitAnimationState] = useState({
    activeId: "",
    playing: false,
    elapsedSec: 0,
    speed: 1
  });
  const implicitAnimationStateRef = useRef(implicitAnimationState);
  const [implicitGraphicsSettings, setImplicitGraphicsSettings] = useState(() => normalizeImplicitGraphicsSettings());
  const [implicitParameterInteractionActive, setImplicitParameterInteractionActive] = useState(false);
  const implicitParameterInteractionTimerRef = useRef(0);
  const [urdfPosePickerState, setUrdfPosePickerState] = useState(emptyUrdfPosePickerState);
  const [pendingCadRefQueryParams, setPendingCadRefQueryParams] = useState(() => readCadRefQueryParams());
  const lastPersistenceFailureKeyRef = useRef("");
  const urdfTrajectoryPlaybackRef = useRef({
    frameId: 0,
    token: 0
  });
  const stepArtifactGenerationRequestsRef = useRef(new Map());
  const selectedStepArtifactBuildKeyRef = useRef("");

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
    meshLoadInProgress,
    meshLoadTargetFile,
    meshLoadStage,
    status,
    setStatus,
    error,
    setError,
    dxfState,
    setDxfState,
    dxfStatus,
    setDxfStatus,
    dxfError,
    setDxfError,
    dxfLoadStage,
    gcodeState,
    setGcodeState,
    gcodeStatus,
    setGcodeStatus,
    gcodeError,
    setGcodeError,
    gcodeLoadStage,
    implicitState,
    setImplicitState,
    implicitStatus,
    setImplicitStatus,
    implicitError,
    setImplicitError,
    implicitLoadStage,
    urdfState,
    setUrdfState,
    urdfStatus,
    setUrdfStatus,
    urdfError,
    setUrdfError,
    urdfLoadStage,
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
    getCachedDxfState,
    getCachedGcodeState,
    getCachedImplicitState,
    getCachedUrdfState,
    cancelMeshLoad,
    cancelDxfLoad,
    cancelGcodeLoad,
    cancelImplicitLoad,
    cancelUrdfLoad,
    cancelReferenceLoad,
    cancelDisplayEdgeLoad,
    loadMeshForEntry,
    loadDxfForEntry,
    loadGcodeForEntry,
    loadImplicitForEntry,
    loadUrdfForEntry,
    loadReferencesForEntry,
    loadDisplayEdgesForEntry
  } = useCadAssets({
    entryHasMesh,
    entryHasReferences,
    entryHasDisplayEdges,
    entryHasDxf,
    entryHasGcode,
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
  const activeStepArtifactGenerationFiles = useMemo(() => {
    const files = Object.values(stepArtifactGenerationStateByKey)
      .filter((state) => state?.status === "loading" && state?.file)
      .map((state) => String(state.file).trim())
      .filter(Boolean);
    return [...new Set(files)];
  }, [stepArtifactGenerationStateByKey]);
  const selectedGeneratorRunning = Boolean(
    catalogSelectedEntry &&
    activeGeneratorFiles.includes(fileKey(catalogSelectedEntry))
  );
  const selectedStepSourceStatusFile = catalogSelectedEntrySourceFormat === RENDER_FORMAT.STEP && catalogSelectedEntry
    ? fileKey(catalogSelectedEntry)
    : "";
  const selectedStepSourceStatusKey = selectedStepSourceStatusFile
    ? [
        selectedStepSourceStatusFile,
        catalogSelectedEntry?.hash || "",
        manifestRevision
      ].join(":")
    : "";
  const selectedStepSourceStatus =
    !selectedGeneratorRunning && selectedStepSourceStatusKey && stepSourceStatusState.key === selectedStepSourceStatusKey
      ? stepSourceStatusState.status
      : null;
  const selectedEntry = useMemo(
    () => mergeStepSourceStatusIntoEntry(catalogSelectedEntry, selectedStepSourceStatus),
    [catalogSelectedEntry, selectedStepSourceStatus]
  );
  const selectedEntrySourceFormat = entrySourceFormat(selectedEntry);
  const selectedFileSheetKind = fileSheetKindForEntry(selectedEntry);
  const directoryOptions = useMemo(
    () => normalizeViewerDirectoryOptions(viewerServerInfo),
    [viewerServerInfo]
  );
  const activeViewerDir = readActiveCadDir({ assetBackend: viewerAssetBackend });
  const activeDirectory = catalogRootDir || activeViewerDir;
  const directorySelectionEligible = !explicitDirParam && !activeDirectory;
  const directorySelectionActive = directorySelectionEligible && directoryOptions.length > 1;
  const directoryAutoEnterDir = directorySelectionEligible && !String(explicitFileParam || "").trim() && directoryOptions.length === 1
    ? directoryOptions[0].dir
    : "";
  const directoryNavigationAvailable = !directorySelectionActive;
  const stepArtifactGenerationAvailable = viewerServerInfo
    ? viewerServerInfo.stepArtifactGenerationAvailable !== false
    : viewerAssetBackend === LOCAL_ASSET_BACKEND;
  const fileAccessBackend = viewerServerInfo ? (viewerServerBackend || "local-fs") : "";
  const fileRevealAvailable = fileAccessBackend === "local-fs";
  const filePathCopyAvailable = fileAccessBackend === "local-fs" && Boolean(
    viewerServerInfo?.rootPath || viewerServerInfo?.directoryRoot
  );
  const fileLinkCopyAvailable = fileAccessBackend === "vercel-blob";
  const isStepView = selectedEntrySourceFormat === RENDER_FORMAT.STEP;
  const isAssemblyView = selectedEntry?.kind === "assembly";
  const isUrdfView = isRobotRenderFormat(selectedEntrySourceFormat);
  const isGcodeView = selectedEntrySourceFormat === RENDER_FORMAT.GCODE;
  const selectedStepModuleUrl = isStepView ? entryStepModuleUrl(selectedEntry) : "";
  const selectedStepModuleCadPath = selectedStepModuleUrl ? cadPathForEntry(selectedEntry) : "";
  const selectedStepModuleDefinition = stepModuleLoadState.url === selectedStepModuleUrl
    ? stepModuleLoadState.definition
    : null;
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
  const selectedEntryHasGcode = entryHasGcode(selectedEntry);
  const selectedEntryHasImplicit = entryHasImplicitAsset(selectedEntry);
  const selectedStepArtifactExternalGenerationActive = stepArtifactGenerationInProgress({
    entry: selectedEntry,
    activeGenerationFiles: activeGeneratorFiles
  });
  const selectedStepArtifactBuildFile = !selectedEntryHasMesh && stepArtifactCanGenerate(
    selectedEntry,
    selectedEntrySourceFormat,
    { generationAvailable: stepArtifactGenerationAvailable || selectedStepArtifactExternalGenerationActive }
  )
    ? fileKey(selectedEntry)
    : "";
  const selectedStepArtifactBuildKey = selectedStepArtifactBuildFile
      ? [
          selectedStepArtifactBuildFile,
          selectedEntry?.hash || "",
          selectedEntry?.artifact?.error || ""
        ].join(":")
    : "";
  const selectedStepArtifactGenerationState = selectedStepArtifactBuildKey
    ? stepArtifactGenerationStateByKey[selectedStepArtifactBuildKey]
    : null;
  const selectedStepArtifactGenerationStatus = selectedStepArtifactGenerationState?.status || "idle";
  const selectedStepArtifactGenerationFailureCount = stepArtifactGenerationFailureCount(
    selectedStepArtifactGenerationState
  );
  const selectedStepArtifactGenerationActive = stepArtifactGenerationInProgress({
    entry: selectedEntry,
    generationState: selectedStepArtifactGenerationState,
    activeGenerationFiles: activeGeneratorFiles
  });
  const selectedStepArtifactRenderPending = Boolean(
    selectedStepArtifactBuildKey &&
    (
      selectedStepArtifactGenerationActive ||
      (
        selectedStepArtifactGenerationStatus !== "error" &&
        selectedStepArtifactGenerationStatus !== "ready"
      )
    )
  );
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
  const selectedDxfMatches =
    !!dxfState &&
    !!selectedEntry &&
    dxfState.file === fileKey(selectedEntry) &&
    dxfState.dxfHash === entryAssetHash(selectedEntry, "dxf");
  const selectedGcodeMatches =
    !!gcodeState &&
    !!selectedEntry &&
    gcodeState.file === fileKey(selectedEntry) &&
    gcodeState.gcodeHash === entryAssetHash(selectedEntry, "gcode");
  const selectedImplicitMatches =
    !!implicitState &&
    !!selectedEntry &&
    implicitState.file === fileKey(selectedEntry) &&
    implicitState.implicitHash === entryAssetHash(selectedEntry, "implicit");
  const selectedUrdfMatches =
    !!urdfState &&
    !!selectedEntry &&
    urdfState.file === fileKey(selectedEntry) &&
    urdfState.urdfHash === entryUrdfAssetHash(selectedEntry);
  const selectedUrdfData = selectedUrdfMatches ? urdfState.urdfData : null;
  const selectedUrdfMeshes = selectedUrdfMatches ? urdfState.meshesByUrl : null;
  const selectedDxfData = selectedDxfMatches ? dxfState.dxfData : null;
  const selectedGcodeData = selectedGcodeMatches ? gcodeState.gcodeData : null;
  const selectedImplicitModel = selectedImplicitMatches ? implicitState.model : null;
  const selectedImplicitDefinition = selectedImplicitModel?.definition || null;
  const selectedDxfFileRef = selectedEntrySourceFormat === RENDER_FORMAT.DXF
    ? fileKey(selectedEntry)
    : "";
  const selectedGcodeFileRef = selectedEntrySourceFormat === RENDER_FORMAT.GCODE
    ? fileKey(selectedEntry)
    : "";
  const selectedUrdfFileRef = isRobotRenderFormat(selectedEntrySourceFormat)
    ? fileKey(selectedEntry)
    : "";
  const defaultSelectedUrdfJointValues = useMemo(
    () => buildDefaultUrdfJointValues(selectedUrdfData),
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
  const selectedUrdfMotion = useMemo(() => {
    const motion = selectedUrdfData?.motion;
    const endEffectors = Array.isArray(motion?.endEffectors) ? motion.endEffectors : [];
    return endEffectors.length ? { ...motion, endEffectors } : null;
  }, [selectedUrdfData]);
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
  const activeSelectedUrdfGroupStateId = useMemo(
    () => (
      selectedUrdfGroupStates.find((state) => jointValueSubsetClose(selectedUrdfJointValues, state.jointValuesByName))?.id || ""
    ),
    [selectedUrdfJointValues, selectedUrdfGroupStates]
  );
  const selectedUrdfMotionConfigKey = useMemo(() => {
    if (!MOVEIT2_SERVER_ENABLED || !selectedUrdfFileRef || !selectedUrdfMotion?.srdf) {
      return "";
    }
    return `${selectedUrdfFileRef}:${entryUrdfAssetHash(selectedEntry) || ""}`;
  }, [selectedEntry, selectedUrdfFileRef, selectedUrdfMotion]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }
    const controller = new AbortController();
    let active = true;
    const url = new URL("/__cad/server", window.location.href);
    const activeViewerDir = readActiveCadDir();
    const activeFile = readCadParam();
    if (activeViewerDir) {
      url.searchParams.set("dir", activeViewerDir);
    }
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
    if (!directoryAutoEnterDir) {
      return;
    }
    writeCadDirParam(directoryAutoEnterDir);
    refreshCadCatalog({ markRefreshing: true }).catch((error) => {
      if (import.meta.env.DEV) {
        console.warn("Failed to refresh CAD catalog", error);
      }
    });
    refreshCadGenerationStatus();
  }, [directoryAutoEnterDir]);

  useEffect(() => {
    let active = true;
    let probeTimer = 0;
    const clearProbeTimer = () => {
      if (!probeTimer) {
        return;
      }
      clearTimeout(probeTimer);
      probeTimer = 0;
    };
    if (!selectedUrdfMotionConfigKey) {
      setMoveIt2ServerLive(false);
      return () => {
        active = false;
        clearProbeTimer();
      };
    }
    setMoveIt2ServerLive(false);
    const probeServer = async () => {
      const live = await checkMoveIt2ServerLive({ timeoutMs: 750 });
      if (!active) {
        return;
      }
      setMoveIt2ServerLive(live);
      probeTimer = setTimeout(probeServer, live ? 5000 : 2000);
    };
    void probeServer();
    return () => {
      active = false;
      clearProbeTimer();
    };
  }, [selectedUrdfMotionConfigKey]);

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
      setStepModuleAnimationState(buildDefaultStepModuleAnimationState(null));
      resetStepAnimationStore();
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
    setStepModuleAnimationState(buildDefaultStepModuleAnimationState(null));
    resetStepAnimationStore();

    loadStepModuleDefinition(selectedStepModuleUrl, { cadPath: selectedStepModuleCadPath }).then((definition) => {
      if (cancelled) {
        return;
      }
      const restoredSessionState = readFileSessionState(
        fileSessionNamespace,
        fileKey(selectedEntry),
        selectedEntry
      );
      const restoredStepModuleState = restoredSessionState?.slices?.stepModule || null;
      const defaultAnimationState = buildDefaultStepModuleAnimationState(definition);
      setStepModuleLoadState({
        url: selectedStepModuleUrl,
        status: "ready",
        error: "",
        definition
      });
      const nextParameterValues = normalizeStepModuleParameterValues(
        definition,
        restoredStepModuleState?.parameterValues || definition.defaultParameterValues
      );
      const nextAnimationState = restoredStepModuleState?.animationState
        ? {
            ...defaultAnimationState,
            ...restoredStepModuleState.animationState,
            activeId: restoredStepModuleState.animationState.activeId || defaultAnimationState.activeId,
            playing: false
          }
        : defaultAnimationState;
      stepModuleParameterValuesRef.current = nextParameterValues;
      stepModuleAnimationStateRef.current = nextAnimationState;
      setStepModuleParameterValues(nextParameterValues);
      setStepModuleEnabled(restoredStepModuleState ? restoredStepModuleState.enabled !== false : true);
      setStepModuleAnimationState(nextAnimationState);
      resetStepAnimationStore({
        elapsedSec: nextAnimationState.elapsedSec,
        parameterValues: nextParameterValues
      });
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
      setStepModuleAnimationState(buildDefaultStepModuleAnimationState(null));
      resetStepAnimationStore();
    });

    return () => {
      cancelled = true;
    };
  }, [fileSessionNamespace, selectedEntry, selectedStepModuleCadPath, selectedStepModuleUrl]);

  useEffect(() => {
    if (!selectedImplicitDefinition || !selectedEntry || selectedEntrySourceFormat !== RENDER_FORMAT.IMPLICIT) {
      setImplicitParameterValues({});
      const nextAnimationState = buildDefaultParameterAnimationState(null);
      implicitAnimationStateRef.current = nextAnimationState;
      setImplicitAnimationState(nextAnimationState);
      return;
    }
    const restoredSessionState = readFileSessionState(
      fileSessionNamespace,
      fileKey(selectedEntry),
      selectedEntry
    );
    const restoredImplicitState = restoredSessionState?.slices?.implicit || null;
    const defaultAnimationState = buildDefaultParameterAnimationState(selectedImplicitDefinition);
    setImplicitParameterValues(normalizeParameterValues(
      selectedImplicitDefinition,
      restoredImplicitState?.parameterValues || selectedImplicitDefinition.defaultParameterValues
    ));
    const nextAnimationState = restoredImplicitState?.animationState
      ? {
          ...defaultAnimationState,
          ...restoredImplicitState.animationState,
          activeId: restoredImplicitState.animationState.activeId || defaultAnimationState.activeId,
          playing: false
        }
      : defaultAnimationState;
    implicitAnimationStateRef.current = nextAnimationState;
    setImplicitAnimationState(nextAnimationState);
  }, [
    fileSessionNamespace,
    selectedEntry,
    selectedEntrySourceFormat,
    selectedImplicitDefinition
  ]);

  const selectedUrdfMotionControls = selectedUrdfMotion;
  const selectedUrdfMoveIt2ActionsEnabled = Boolean(moveit2ServerLive && selectedUrdfMotionControls);
  const selectedUrdfMotionState = useMemo(() => {
    if (!selectedUrdfFileRef) {
      return {};
    }
    const state = urdfMotionStateByFileRef?.[selectedUrdfFileRef];
    return state && typeof state === "object" ? state : {};
  }, [selectedUrdfFileRef, urdfMotionStateByFileRef]);
  const selectedUrdfMotionPlanningGroups = selectedUrdfMotionControls?.planningGroups || EMPTY_LIST;
  const selectedUrdfMotionPlanningGroupName = useMemo(() => {
    const storedName = String(selectedUrdfMotionState.activePlanningGroupName || "").trim();
    if (storedName && selectedUrdfMotionPlanningGroups.some((group) => String(group?.name || "").trim() === storedName)) {
      return storedName;
    }
    return String(selectedUrdfMotionPlanningGroups[0]?.name || "").trim();
  }, [selectedUrdfMotionPlanningGroups, selectedUrdfMotionState.activePlanningGroupName]);
  const selectedUrdfMotionEndEffectors = selectedUrdfMotionControls?.endEffectors || EMPTY_LIST;
  const selectedUrdfMotionEndEffectorName = useMemo(() => {
    const storedName = String(selectedUrdfMotionState.activeEndEffectorName || "").trim();
    if (storedName && selectedUrdfMotionEndEffectors.some((endEffector) => String(endEffector?.name || "").trim() === storedName)) {
      return storedName;
    }
    return String(selectedUrdfMotionEndEffectors[0]?.name || "").trim();
  }, [selectedUrdfMotionEndEffectors, selectedUrdfMotionState.activeEndEffectorName]);
  const selectedUrdfMotionEndEffector = useMemo(() => (
    selectedUrdfMotionEndEffectors.find((endEffector) => String(endEffector?.name || "").trim() === selectedUrdfMotionEndEffectorName) || null
  ), [selectedUrdfMotionEndEffectorName, selectedUrdfMotionEndEffectors]);
  const selectedUrdfMotionTargetFrames = useMemo(() => (
    Array.isArray(selectedUrdfData?.links)
      ? selectedUrdfData.links.map((link) => String(link?.name || "").trim()).filter(Boolean)
      : []
  ), [selectedUrdfData]);
  const selectedUrdfMotionTargetFrameName = useMemo(() => {
    const storedName = String(selectedUrdfMotionState.targetFrame || "").trim();
    if (storedName && selectedUrdfMotionTargetFrames.includes(storedName)) {
      return storedName;
    }
    if (selectedUrdfData?.rootLink && selectedUrdfMotionTargetFrames.includes(selectedUrdfData.rootLink)) {
      return selectedUrdfData.rootLink;
    }
    return selectedUrdfMotionTargetFrames[0] || "";
  }, [selectedUrdfData, selectedUrdfMotionState.targetFrame, selectedUrdfMotionTargetFrames]);
  const selectedUrdfMoveIt2Settings = useMemo(() => ({
    planningGroup: selectedUrdfMotionPlanningGroupName,
    endEffector: selectedUrdfMotionEndEffectorName,
    targetFrame: selectedUrdfMotionTargetFrameName,
    ikTimeout: Math.max(toFiniteNumber(selectedUrdfMotionState.ikTimeout, 0.05), 0.001),
    ikAttempts: Math.max(Math.round(toFiniteNumber(selectedUrdfMotionState.ikAttempts, 1)), 1),
    ikTolerance: Math.max(toFiniteNumber(selectedUrdfMotionState.ikTolerance, 0.002), 0.0001),
    planningPipeline: String(selectedUrdfMotionState.planningPipeline || "ompl").trim() || "ompl",
    plannerId: String(selectedUrdfMotionState.plannerId || "RRTConnectkConfigDefault").trim() || "RRTConnectkConfigDefault",
    planningTime: Math.max(toFiniteNumber(selectedUrdfMotionState.planningTime, 1), 0.1),
    maxVelocityScalingFactor: Math.min(Math.max(toFiniteNumber(selectedUrdfMotionState.maxVelocityScalingFactor, 1), 0.01), 1),
    maxAccelerationScalingFactor: Math.min(Math.max(toFiniteNumber(selectedUrdfMotionState.maxAccelerationScalingFactor, 1), 0.01), 1)
  }), [
    selectedUrdfMotionEndEffectorName,
    selectedUrdfMotionPlanningGroupName,
    selectedUrdfMotionState,
    selectedUrdfMotionTargetFrameName
  ]);
  const selectedUrdfMotionCurrentPosition = useMemo(() => {
    if (!selectedUrdfData || !selectedUrdfMotionEndEffector || !selectedUrdfMotionTargetFrameName) {
      return null;
    }
    return linkOriginInFrame(
      selectedUrdfData,
      selectedUrdfJointValues,
      selectedUrdfMotionEndEffector.link,
      selectedUrdfMotionTargetFrameName
    );
  }, [selectedUrdfData, selectedUrdfMotionEndEffector, selectedUrdfJointValues, selectedUrdfMotionTargetFrameName]);
  const selectedUrdfMotionTargetPosition = useMemo(() => {
    const targetsByEndEffector = selectedUrdfMotionState.targetsByEndEffector && typeof selectedUrdfMotionState.targetsByEndEffector === "object"
      ? selectedUrdfMotionState.targetsByEndEffector
      : {};
    const storedTarget = selectedUrdfMotionEndEffectorName ? targetsByEndEffector[selectedUrdfMotionEndEffectorName] : null;
    return normalizeMotionTargetPosition(storedTarget, selectedUrdfMotionCurrentPosition || [0, 0, 0]);
  }, [selectedUrdfMotionCurrentPosition, selectedUrdfMotionEndEffectorName, selectedUrdfMotionState.targetsByEndEffector]);
  const selectedUrdfMotionSolving = Boolean(
    selectedUrdfMotionEndEffectorName &&
    selectedUrdfMotionState.solvingEndEffectorName === selectedUrdfMotionEndEffectorName
  );
  const selectedUrdfPosePickerState = selectedUrdfFileRef && urdfPosePickerState.fileRef === selectedUrdfFileRef
    ? urdfPosePickerState
    : null;
  const urdfPosePickerActive = Boolean(
    selectedUrdfFileRef &&
    selectedUrdfMoveIt2ActionsEnabled &&
    selectedUrdfPosePickerState
  );
  const selectedUrdfMeshGeometryResult = useMemo(() => {
    if (!selectedUrdfData || !selectedUrdfMeshes) {
      return {
        meshData: null,
        error: ""
      };
    }
    try {
      return {
        meshData: buildUrdfMeshGeometry(selectedUrdfData, selectedUrdfMeshes),
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
  const selectedGcodeLayerCount = Array.isArray(selectedGcodeData?.layers)
    ? selectedGcodeData.layers.length
    : 0;
  const selectedGcodeMaxLayer = selectedGcodeLayerCount > 0
    ? Math.min(
        Math.max(
          Number.isFinite(Number(gcodeMaxLayer)) ? Math.trunc(Number(gcodeMaxLayer)) : selectedGcodeLayerCount - 1,
          0
        ),
        selectedGcodeLayerCount - 1
      )
    : 0;
  const selectedGcodePreviewOptions = useMemo(() => normalizeGcodePreviewOptions({
    showTravel: gcodeShowTravel,
    layerRange: [0, selectedGcodeMaxLayer],
    detailMode: gcodeFullDetail ? "full" : "adaptive",
    detailLevel: gcodePreviewDetailLevel
  }, selectedGcodeLayerCount), [
    gcodeFullDetail,
    gcodePreviewDetailLevel,
    gcodeShowTravel,
    selectedGcodeLayerCount,
    selectedGcodeMaxLayer
  ]);
  const selectedGcodePreview = useMemo(() => {
    if (!selectedGcodeData) {
      return {
        meshData: null,
        error: ""
      };
    }
    try {
      return {
        meshData: buildGcodePreviewMeshData(selectedGcodeData, selectedGcodePreviewOptions),
        error: ""
      };
    } catch (error) {
      return {
        meshData: null,
        error: error instanceof Error ? error.message : String(error)
      };
    }
  }, [selectedGcodeData, selectedGcodePreviewOptions]);
  const selectedGcodeMeshData = selectedGcodePreview.meshData;
  const selectedGcodePreviewError = selectedGcodePreview.error;
  const selectedGcodePreviewKey = useMemo(() => {
    if (!selectedGcodeFileRef || !selectedGcodeData) {
      return selectedGcodeFileRef;
    }
    return `${selectedGcodeFileRef}:travel=${gcodeShowTravel ? "1" : "0"}:layer=${selectedGcodeMaxLayer}:detail=${gcodeFullDetail ? "full" : `adaptive-${gcodePreviewDetailLevel}`}`;
  }, [
    gcodeFullDetail,
    gcodePreviewDetailLevel,
    gcodeShowTravel,
    selectedGcodeData,
    selectedGcodeFileRef,
    selectedGcodeMaxLayer
  ]);
  useEffect(() => {
    if (!selectedGcodeFileRef || selectedGcodeLayerCount <= 0) {
      setGcodeMaxLayer(null);
      return;
    }
    setGcodeMaxLayer(selectedGcodeLayerCount - 1);
    setGcodeFullDetail(false);
    setGcodePreviewDetailLevel(DEFAULT_GCODE_PREVIEW_DETAIL_LEVEL);
  }, [selectedGcodeFileRef, selectedGcodeLayerCount]);
  const selectedMeshData = isRobotRenderFormat(selectedEntrySourceFormat)
    ? selectedUrdfPreview.meshData
    : isGcodeView
      ? selectedGcodeMeshData
      : selectedMeshMatches
        ? meshState.meshData
        : null;
  const selectedStepModuleActiveAnimation = useMemo(
    () => findStepModuleAnimation(selectedStepModuleDefinition, stepModuleAnimationState.activeId),
    [selectedStepModuleDefinition, stepModuleAnimationState.activeId]
  );
  const selectedStepModuleAnimationViewState = useMemo(() => ({
    ...stepModuleAnimationState,
    activeId: selectedStepModuleActiveAnimation?.id || stepModuleAnimationState.activeId || "",
    duration: selectedStepModuleActiveAnimation?.duration || 0,
    loop: selectedStepModuleActiveAnimation?.loop !== false
  }), [selectedStepModuleActiveAnimation, stepModuleAnimationState]);
  const selectedStepParameterRuntime = useMemo(() => {
    if (!selectedStepModuleDefinition || !stepModuleEnabled) {
      return null;
    }
    return {
      definition: selectedStepModuleDefinition,
      parameterValues: normalizeStepModuleParameterValues(selectedStepModuleDefinition, stepModuleParameterValues),
      animationState: selectedStepModuleAnimationViewState,
      cadPath: selectedStepModuleDefinition.cadPath || selectedStepModuleCadPath,
      sourceUrl: selectedStepModuleUrl
    };
  }, [
    selectedStepModuleAnimationViewState,
    selectedStepModuleCadPath,
    selectedStepModuleDefinition,
    selectedStepModuleUrl,
    stepModuleEnabled,
    stepModuleParameterValues
  ]);
  const handleStepModuleTransformDetectedChange = useCallback(() => {}, []);
  const stepModuleTreeSelectionDisabled = false;
  const stepModuleTreeSelectionDisabledReason = "";

  useEffect(() => {
    stepModuleParameterValuesRef.current = stepModuleParameterValues;
  }, [stepModuleParameterValues]);

  useEffect(() => {
    stepModuleAnimationStateRef.current = stepModuleAnimationState;
  }, [stepModuleAnimationState]);

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

  const handleCopyStepModuleParams = useCallback(async () => {
    setScreenshotStatus("");
    if (!selectedStepModuleDefinition?.parameters?.length) {
      setCopyStatus("No STEP parameters to copy");
      return;
    }
    try {
      await copyTextToClipboard(buildStepModuleParamsCopyText(
        selectedStepModuleDefinition,
        stepModuleParameterValues
      ));
      setCopyStatus("Copied STEP parameters");
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "Clipboard write failed");
    }
  }, [selectedStepModuleDefinition, stepModuleParameterValues]);

  const handlePasteStepModuleParams = useCallback(async () => {
    setScreenshotStatus("");
    if (!selectedStepModuleDefinition?.parameters?.length) {
      setCopyStatus("No STEP parameters to paste");
      return;
    }
    try {
      const clipboardText = await readTextFromClipboard();
      const { values, count } = parseStepModuleParamsPasteText(selectedStepModuleDefinition, clipboardText);
      setStepModuleParameterValues((current) => ({
        ...current,
        ...values
      }));
      setCopyStatus(`Pasted ${count} STEP param${count === 1 ? "" : "s"}`);
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "Clipboard paste failed");
    }
  }, [selectedStepModuleDefinition]);

  const handleResetStepModuleParameters = useCallback(() => {
    if (!selectedStepModuleDefinition) {
      return;
    }
    const nextParameterValues = normalizeStepModuleParameterValues(
      selectedStepModuleDefinition,
      selectedStepModuleDefinition.defaultParameterValues
    );
    const nextAnimationState = buildDefaultStepModuleAnimationState(selectedStepModuleDefinition);
    stepModuleParameterValuesRef.current = nextParameterValues;
    stepModuleAnimationStateRef.current = nextAnimationState;
    setStepModuleParameterValues(nextParameterValues);
    setStepModuleAnimationState(nextAnimationState);
    resetStepAnimationStore({
      elapsedSec: nextAnimationState.elapsedSec,
      parameterValues: nextParameterValues
    });
  }, [selectedStepModuleDefinition]);

  const handleStepModuleAnimationSelect = useCallback((animationId) => {
    const animation = findStepModuleAnimation(selectedStepModuleDefinition, animationId);
    const nextState = {
      ...stepModuleAnimationStateRef.current,
      activeId: animation?.id || "",
      playing: false,
      elapsedSec: 0
    };
    stepModuleAnimationStateRef.current = nextState;
    resetStepAnimationStore({
      elapsedSec: 0,
      parameterValues: stepModuleParameterValuesRef.current
    });
    setStepModuleAnimationState(nextState);
  }, [selectedStepModuleDefinition]);

  const handleStepModuleAnimationPlayToggle = useCallback(() => {
    const currentState = stepModuleAnimationStateRef.current;
    const animation = findStepModuleAnimation(selectedStepModuleDefinition, currentState.activeId);
    if (!animation) {
      return;
    }
    const duration = Math.max(Number(animation.duration) || 0, 0.001);
    if (currentState.playing) {
      const elapsedSec = clampNumber(getStepAnimationElapsed(), 0, duration);
      const liveValues = getStepAnimationParameterValues();
      const nextValues = liveValues && typeof liveValues === "object" && Object.keys(liveValues).length
        ? liveValues
        : stepModuleParameterValuesRef.current;
      stepModuleParameterValuesRef.current = nextValues;
      setStepModuleParameterValues(nextValues);
      setStepAnimationFrame({ elapsedSec, parameterValues: nextValues });
      const nextState = {
        ...currentState,
        activeId: animation.id,
        elapsedSec,
        playing: false
      };
      stepModuleAnimationStateRef.current = nextState;
      setStepModuleAnimationState(nextState);
      return;
    }
    const elapsedSec = currentState.elapsedSec >= duration
      ? 0
      : clampNumber(currentState.elapsedSec, 0, duration);
    setStepAnimationElapsed(elapsedSec);
    const nextState = {
      ...currentState,
      activeId: animation.id,
      elapsedSec,
      playing: true
    };
    stepModuleAnimationStateRef.current = nextState;
    setStepModuleAnimationState(nextState);
  }, [selectedStepModuleDefinition]);

  const handleStepModuleAnimationReset = useCallback(() => {
    const currentState = stepModuleAnimationStateRef.current;
    const animation = findStepModuleAnimation(selectedStepModuleDefinition, currentState.activeId);
    const nextValues = selectedStepModuleDefinition && animation
      ? buildStepModuleAnimationFrameValues({
          definition: selectedStepModuleDefinition,
          animation,
          elapsedSec: 0,
          speed: currentState.speed,
          parameterValues: stepModuleParameterValuesRef.current
        })
      : stepModuleParameterValuesRef.current;
    stepModuleParameterValuesRef.current = nextValues;
    setStepModuleParameterValues((current) => (
      shallowObjectValuesEqual(current, nextValues) ? current : nextValues
    ));
    resetStepAnimationStore({ elapsedSec: 0, parameterValues: nextValues });
    const nextState = {
      ...currentState,
      elapsedSec: 0,
      playing: false
    };
    stepModuleAnimationStateRef.current = nextState;
    setStepModuleAnimationState(nextState);
  }, [selectedStepModuleDefinition]);

  const handleStepModuleAnimationScrub = useCallback((elapsedSec) => {
    const duration = Math.max(Number(selectedStepModuleActiveAnimation?.duration) || 1, 0.001);
    const clampedElapsedSec = clampNumber(elapsedSec, 0, duration);
    setStepAnimationElapsed(clampedElapsedSec);
    const nextState = {
      ...stepModuleAnimationStateRef.current,
      elapsedSec: clampedElapsedSec
    };
    stepModuleAnimationStateRef.current = nextState;
    setStepModuleAnimationState(nextState);
  }, [selectedStepModuleActiveAnimation]);

  const handleStepModuleAnimationSpeedChange = useCallback((speed) => {
    const nextState = {
      ...stepModuleAnimationStateRef.current,
      speed: clampNumber(speed, 0.1, 5)
    };
    stepModuleAnimationStateRef.current = nextState;
    setStepModuleAnimationState(nextState);
  }, []);

  const handleStepModuleEnabledChange = useCallback((enabled) => {
    const nextEnabled = enabled !== false;
    setStepModuleEnabled(nextEnabled);
    if (!nextEnabled) {
      const nextState = {
        ...stepModuleAnimationStateRef.current,
        playing: false
      };
      stepModuleAnimationStateRef.current = nextState;
      setStepModuleAnimationState(nextState);
    }
  }, []);

  useEffect(() => {
    if (
      !selectedStepModuleDefinition ||
      !stepModuleEnabled ||
      !selectedStepModuleActiveAnimation ||
      !stepModuleAnimationState.playing ||
      typeof window === "undefined" ||
      typeof window.requestAnimationFrame !== "function"
    ) {
      return undefined;
    }

    const definition = selectedStepModuleDefinition;
    const animation = selectedStepModuleActiveAnimation;
    const duration = Math.max(Number(animation.duration) || 1, 0.001);
    let frameId = 0;
    let previousTimeMs = animationNowMs();
    setStepAnimationElapsed(clampNumber(stepModuleAnimationStateRef.current.elapsedSec, 0, duration));

    const tick = (timeMs) => {
      const currentState = stepModuleAnimationStateRef.current;
      if (!currentState.playing || currentState.activeId !== animation.id) {
        return;
      }
      const deltaSec = Math.max((timeMs - previousTimeMs) / 1000, 0);
      previousTimeMs = timeMs;
      const speed = clampNumber(currentState.speed, 0.1, 5);
      let elapsedSec = getStepAnimationElapsed() + (deltaSec * speed);
      let playing = currentState.playing;
      if (animation.loop !== false) {
        elapsedSec %= duration;
      } else if (elapsedSec >= duration) {
        elapsedSec = duration;
        playing = false;
      }
      const nextValues = buildStepModuleAnimationFrameValues({
        definition,
        animation,
        elapsedSec,
        speed,
        parameterValues: stepModuleParameterValuesRef.current
      });
      setStepAnimationFrame({ elapsedSec, parameterValues: nextValues });
      if (!playing) {
        stepModuleParameterValuesRef.current = nextValues;
        setStepModuleParameterValues((current) => (
          shallowObjectValuesEqual(current, nextValues) ? current : nextValues
        ));
        const nextState = {
          ...currentState,
          elapsedSec,
          speed,
          playing: false
        };
        stepModuleAnimationStateRef.current = nextState;
        setStepModuleAnimationState(nextState);
        return;
      }
      frameId = window.requestAnimationFrame(tick);
    };

    frameId = window.requestAnimationFrame(tick);
    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [
    selectedStepModuleActiveAnimation,
    selectedStepModuleDefinition,
    stepModuleEnabled,
    stepModuleAnimationState.playing
  ]);

  useEffect(() => {
    const animation = selectedStepModuleActiveAnimation;
    if (!selectedStepModuleDefinition || !stepModuleEnabled || typeof animation?.update !== "function") {
      resetStepAnimationStore({
        elapsedSec: 0,
        parameterValues: stepModuleParameterValuesRef.current
      });
      return;
    }
    if (stepModuleAnimationState.playing) {
      return;
    }
    const duration = Math.max(Number(animation.duration) || 1, 0.001);
    const elapsedSec = clampNumber(stepModuleAnimationState.elapsedSec, 0, duration);
    const nextValues = buildStepModuleAnimationFrameValues({
      definition: selectedStepModuleDefinition,
      animation,
      elapsedSec,
      speed: stepModuleAnimationState.speed,
      parameterValues: stepModuleParameterValuesRef.current
    });
    stepModuleParameterValuesRef.current = nextValues;
    setStepModuleParameterValues((current) => (
      shallowObjectValuesEqual(current, nextValues) ? current : nextValues
    ));
    setStepAnimationFrame({ elapsedSec, parameterValues: nextValues });
  }, [
    selectedStepModuleActiveAnimation,
    selectedStepModuleDefinition,
    stepModuleEnabled,
    stepModuleAnimationState.elapsedSec,
    stepModuleAnimationState.playing,
    stepModuleAnimationState.speed
  ]);

  const selectedImplicitActiveAnimation = useMemo(
    () => findParameterAnimation(selectedImplicitDefinition, implicitAnimationState.activeId),
    [implicitAnimationState.activeId, selectedImplicitDefinition]
  );
  const selectedImplicitAnimationViewState = useMemo(() => ({
    ...implicitAnimationState,
    activeId: selectedImplicitActiveAnimation?.id || implicitAnimationState.activeId || "",
    duration: selectedImplicitActiveAnimation?.duration || 0,
    loop: selectedImplicitActiveAnimation?.loop !== false
  }), [implicitAnimationState, selectedImplicitActiveAnimation]);
  const implicitRenderParameterValues = useThrottledValue(
    implicitParameterValues,
    IMPLICIT_PARAMETER_RENDER_THROTTLE_MS,
    selectedKey
  );
  const implicitRenderAnimationViewState = useThrottledValue(
    selectedImplicitAnimationViewState,
    IMPLICIT_PARAMETER_RENDER_THROTTLE_MS,
    selectedKey
  );
  const selectedImplicitRuntime = useMemo(() => {
    if (!selectedImplicitModel) {
      return {
        model: null,
        error: ""
      };
    }
    if (!selectedImplicitDefinition?.buildModel) {
      return {
        model: selectedImplicitModel,
        error: ""
      };
    }
    try {
      return {
        model: selectedImplicitDefinition.buildModel(
          implicitRenderParameterValues,
          implicitRenderAnimationViewState
        ),
        error: ""
      };
    } catch (error) {
      return {
        model: null,
        error: error instanceof Error ? error.message : String(error)
      };
    }
  }, [
    implicitRenderAnimationViewState,
    implicitRenderParameterValues,
    selectedImplicitDefinition,
    selectedImplicitModel
  ]);
  const selectedImplicitRuntimeModel = selectedImplicitRuntime.model;
  const selectedImplicitRuntimeError = selectedImplicitRuntime.error;
  useEffect(() => {
    implicitAnimationStateRef.current = implicitAnimationState;
  }, [implicitAnimationState]);

  const markImplicitParameterInteraction = useCallback(() => {
    if (typeof window === "undefined" || typeof window.setTimeout !== "function") {
      return;
    }
    if (implicitParameterInteractionTimerRef.current) {
      window.clearTimeout(implicitParameterInteractionTimerRef.current);
    }
    setImplicitParameterInteractionActive(true);
    implicitParameterInteractionTimerRef.current = window.setTimeout(() => {
      implicitParameterInteractionTimerRef.current = 0;
      setImplicitParameterInteractionActive(false);
    }, IMPLICIT_DYNAMIC_RENDER_SETTLE_MS);
  }, []);

  useEffect(() => {
    return () => {
      if (implicitParameterInteractionTimerRef.current && typeof window !== "undefined") {
        window.clearTimeout(implicitParameterInteractionTimerRef.current);
        implicitParameterInteractionTimerRef.current = 0;
      }
    };
  }, []);

  const implicitRenderPending = !shallowObjectValuesEqual(
    implicitParameterValues,
    implicitRenderParameterValues
  ) || selectedImplicitAnimationViewState.elapsedSec !== implicitRenderAnimationViewState.elapsedSec;
  const implicitDynamicRenderActive = Boolean(
    selectedImplicitModel &&
    (
      implicitAnimationState.playing ||
      implicitParameterInteractionActive ||
      implicitRenderPending
    )
  );

  const handleImplicitParameterChange = useCallback((parameterId, value) => {
    const id = String(parameterId || "").trim();
    const parameter = selectedImplicitDefinition?.parameterMap?.[id];
    if (!parameter) {
      return;
    }
    const nextValue = normalizeParameterValue(parameter, value);
    markImplicitParameterInteraction();
    setImplicitParameterValues((current) => (
      current?.[id] === nextValue
        ? current
        : {
            ...current,
            [id]: nextValue
          }
    ));
  }, [markImplicitParameterInteraction, selectedImplicitDefinition]);

  const handleCopyImplicitParams = useCallback(async () => {
    setScreenshotStatus("");
    if (!selectedImplicitDefinition?.parameters?.length) {
      setCopyStatus("No implicit parameters to copy");
      return;
    }
    try {
      await copyTextToClipboard(buildParameterValuesCopyText(
        selectedImplicitDefinition,
        implicitParameterValues
      ));
      setCopyStatus("Copied implicit parameters");
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "Clipboard write failed");
    }
  }, [implicitParameterValues, selectedImplicitDefinition]);

  const handlePasteImplicitParams = useCallback(async () => {
    setScreenshotStatus("");
    if (!selectedImplicitDefinition?.parameters?.length) {
      setCopyStatus("No implicit parameters to paste");
      return;
    }
    try {
      const clipboardText = await readTextFromClipboard();
      const { values, count } = parseParameterValuesPasteText(selectedImplicitDefinition, clipboardText, {
        label: "implicit parameter",
        unknownLabel: "implicit parameter"
      });
      markImplicitParameterInteraction();
      setImplicitParameterValues((current) => ({
        ...current,
        ...values
      }));
      setCopyStatus(`Pasted ${count} implicit param${count === 1 ? "" : "s"}`);
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "Clipboard paste failed");
    }
  }, [markImplicitParameterInteraction, selectedImplicitDefinition]);

  const handleResetImplicitParameters = useCallback(() => {
    if (!selectedImplicitDefinition) {
      return;
    }
    markImplicitParameterInteraction();
    setImplicitParameterValues(normalizeParameterValues(
      selectedImplicitDefinition,
      selectedImplicitDefinition.defaultParameterValues
    ));
    const nextAnimationState = buildDefaultParameterAnimationState(selectedImplicitDefinition);
    implicitAnimationStateRef.current = nextAnimationState;
    setImplicitAnimationState(nextAnimationState);
  }, [markImplicitParameterInteraction, selectedImplicitDefinition]);

  const handleImplicitAnimationSelect = useCallback((animationId) => {
    const animation = findParameterAnimation(selectedImplicitDefinition, animationId);
    setImplicitAnimationState((current) => {
      const nextState = {
        ...current,
        activeId: animation?.id || "",
        playing: false,
        elapsedSec: 0
      };
      implicitAnimationStateRef.current = nextState;
      return nextState;
    });
  }, [selectedImplicitDefinition]);

  const handleImplicitAnimationPlayToggle = useCallback(() => {
    setImplicitAnimationState((current) => {
      const animation = findParameterAnimation(selectedImplicitDefinition, current.activeId);
      if (!animation) {
        return current;
      }
      const duration = Math.max(Number(animation.duration) || 0, 0.001);
      const elapsedSec = current.elapsedSec >= duration ? 0 : current.elapsedSec;
      const nextState = {
        ...current,
        activeId: animation.id,
        elapsedSec,
        playing: !current.playing
      };
      implicitAnimationStateRef.current = nextState;
      return nextState;
    });
  }, [selectedImplicitDefinition]);

  const handleImplicitAnimationReset = useCallback(() => {
    setImplicitAnimationState((current) => {
      const nextState = {
        ...current,
        elapsedSec: 0,
        playing: false
      };
      implicitAnimationStateRef.current = nextState;
      return nextState;
    });
  }, []);

  const handleImplicitAnimationScrub = useCallback((elapsedSec) => {
    const duration = Math.max(Number(selectedImplicitActiveAnimation?.duration) || 1, 0.001);
    markImplicitParameterInteraction();
    setImplicitAnimationState((current) => {
      const nextState = {
        ...current,
        elapsedSec: clampNumber(elapsedSec, 0, duration)
      };
      implicitAnimationStateRef.current = nextState;
      return nextState;
    });
  }, [markImplicitParameterInteraction, selectedImplicitActiveAnimation]);

  const handleImplicitAnimationSpeedChange = useCallback((speed) => {
    setImplicitAnimationState((current) => {
      const nextState = {
        ...current,
        speed: clampNumber(speed, 0.1, 5)
      };
      implicitAnimationStateRef.current = nextState;
      return nextState;
    });
  }, []);

  useEffect(() => {
    if (
      !selectedImplicitDefinition ||
      !selectedImplicitActiveAnimation ||
      !implicitAnimationState.playing ||
      typeof window === "undefined" ||
      typeof window.setTimeout !== "function"
    ) {
      return undefined;
    }

    let previousTimeMs = animationNowMs();
    let timerId = 0;
    const tick = () => {
      const timeMs = animationNowMs();
      const deltaSec = Math.min(Math.max((timeMs - previousTimeMs) / 1000, 0), 0.25);
      previousTimeMs = timeMs;
      const current = implicitAnimationStateRef.current;
      if (current.playing && current.activeId === selectedImplicitActiveAnimation.id) {
        const duration = Math.max(Number(selectedImplicitActiveAnimation.duration) || 1, 0.001);
        const speed = clampNumber(current.speed, 0.1, 5);
        let elapsedSec = current.elapsedSec + (deltaSec * speed);
        let playing = current.playing;
        if (selectedImplicitActiveAnimation.loop !== false) {
          elapsedSec %= duration;
        } else if (elapsedSec >= duration) {
          elapsedSec = duration;
          playing = false;
        }
        const nextState = {
          ...current,
          elapsedSec,
          speed,
          playing
        };
        implicitAnimationStateRef.current = nextState;
        setImplicitAnimationState(nextState);
        setImplicitParameterValues((currentValues) => {
          try {
            const nextValues = buildAnimatedImplicitParameterValues(
              selectedImplicitDefinition,
              selectedImplicitActiveAnimation,
              currentValues,
              elapsedSec
            );
            return shallowObjectValuesEqual(currentValues, nextValues) ? currentValues : nextValues;
          } catch (error) {
            console.error("Implicit parameter animation update failed", error);
            return currentValues;
          }
        });
      }
      timerId = window.setTimeout(tick, IMPLICIT_PARAMETER_ANIMATION_TICK_MS);
    };

    timerId = window.setTimeout(tick, IMPLICIT_PARAMETER_ANIMATION_TICK_MS);
    return () => {
      window.clearTimeout(timerId);
    };
  }, [
    implicitAnimationState.playing,
    selectedImplicitActiveAnimation,
    selectedImplicitDefinition
  ]);

  useEffect(() => {
    const animation = selectedImplicitActiveAnimation;
    if (!selectedImplicitDefinition || typeof animation?.update !== "function") {
      return;
    }
    setImplicitParameterValues((current) => {
      try {
        const nextValues = buildAnimatedImplicitParameterValues(
          selectedImplicitDefinition,
          animation,
          current,
          implicitAnimationState.elapsedSec
        );
        return shallowObjectValuesEqual(current, nextValues) ? current : nextValues;
      } catch (error) {
        console.error("Implicit parameter animation update failed", error);
        return current;
      }
    });
  }, [
    implicitAnimationState.elapsedSec,
    selectedImplicitActiveAnimation,
    selectedImplicitDefinition
  ]);
  const assemblyRoot = selectedAssemblyStructureReady
    ? selectedMeshData?.assemblyRoot || null
    : null;
  const selectedAssemblyMates = selectedAssemblyStructureReady && Array.isArray(selectedMeshData?.assemblyMates)
    ? selectedMeshData.assemblyMates
    : [];
  const selectedAssemblyMateMap = useMemo(() => {
    const map = new Map();
    for (const mate of selectedAssemblyMates) {
      const mateId = String(mate?.id || "").trim();
      if (mateId) {
        map.set(mateId, mate);
      }
    }
    return map;
  }, [selectedAssemblyMates]);
  const stepTreeRoot = useMemo(() => {
    if (!isStepView) {
      return null;
    }
    return buildStepTreeRoot({
      selectedEntry,
      assemblyRoot,
      meshData: selectedMeshData
    });
  }, [assemblyRoot, isStepView, selectedEntry, selectedMeshData]);
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
  const assemblyCurrentNodeId = assemblyRootNodeId;
  const assemblyCurrentNode = useMemo(
    () => findAssemblyNode(assemblyRoot, assemblyCurrentNodeId) || assemblyRoot,
    [assemblyCurrentNodeId, assemblyRoot]
  );
  const focusedAssemblyInteractionId = useMemo(
    () => (isAssemblyView ? focusedAssemblyInteractionNodeId(assemblyRoot, focusedAssemblyNodeIds) : ""),
    [assemblyRoot, focusedAssemblyNodeIds, isAssemblyView]
  );
  const assemblyInteractionNodeId = focusedAssemblyInteractionId || assemblyCurrentNodeId;
  const assemblyInteractionNode = useMemo(
    () => findAssemblyNode(assemblyRoot, assemblyInteractionNodeId) || assemblyRoot,
    [assemblyInteractionNodeId, assemblyRoot]
  );
  const selectableAssemblyNodeIds = useMemo(
    () => {
      if (!isAssemblyView) {
        return [];
      }
      const focusedNodeIdSet = new Set(focusedAssemblyNodeIds);
      return selectableAssemblyNodeIdsForInspection(assemblyRoot, assemblyInteractionNodeId)
        .filter((nodeId) => !focusedNodeIdSet.has(String(nodeId || "").trim()));
    },
    [assemblyInteractionNodeId, assemblyRoot, focusedAssemblyNodeIds, isAssemblyView]
  );
  const selectableAssemblyNodeIdSet = useMemo(
    () => new Set(selectableAssemblyNodeIds),
    [selectableAssemblyNodeIds]
  );
  const treeSelectableAssemblyNodeIds = useMemo(
    () => (isAssemblyView
      ? selectableTreeNodeIdsForIsolation(assemblyRoot, focusedAssemblyNodeIds, assemblyRootNodeId)
      : []),
    [assemblyRoot, assemblyRootNodeId, focusedAssemblyNodeIds, isAssemblyView]
  );
  const treeSelectableAssemblyNodeIdSet = useMemo(
    () => new Set(treeSelectableAssemblyNodeIds),
    [treeSelectableAssemblyNodeIds]
  );
  const assemblyParts = useMemo(() => {
    return String(assemblyInteractionNode?.nodeType || "").trim() === "assembly"
      ? (Array.isArray(assemblyInteractionNode?.children) ? assemblyInteractionNode.children : []).map((node) => ({
        ...node,
        leafPartIds: descendantLeafPartIds(node)
      }))
      : [];
  }, [assemblyInteractionNode]);
  const assemblyPickPartIdMap = useMemo(() => {
    return buildAssemblyLeafToNodePickMap(assemblyParts);
  }, [assemblyParts]);
  const assemblyPartsLoaded = isAssemblyView
    ? selectedAssemblyStructureReady
    : isStepView && selectedMeshMatches && !!selectedMeshData;
  const supportsPartSelection = isStepView && assemblyPartsLoaded && stepLeafParts.length > 0;
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
  const validAssemblySelectionIds = useMemo(
    () => stepTreeNodes.map((node) => String(node?.id || "").trim()).filter(Boolean),
    [stepTreeNodes]
  );
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
  const selectedUrdfPreviewError = selectedUrdfPreview.error;
  const selectedDxfBendLines = useMemo(() => {
    if (!selectedDxfData) {
      return [];
    }
    try {
      return extractOrderedDxfBendLines(selectedDxfData);
    } catch {
      return [];
    }
  }, [selectedDxfData]);
  const normalizedSelectedDxfBendSettings = useMemo(() => {
    if (!selectedDxfData) {
      return [];
    }
    try {
      return normalizeDxfBendSettings(selectedDxfData, dxfBendSettings);
    } catch {
      return [];
    }
  }, [dxfBendSettings, selectedDxfData]);
  const effectiveDxfThicknessMm = useMemo(() => {
    return normalizeDxfPreviewThicknessMm(
      dxfThicknessMm,
      toFiniteNumber(selectedDxfData?.defaultThicknessMm, DEFAULT_DXF_PREVIEW_THICKNESS_MM)
    );
  }, [dxfThicknessMm, selectedDxfData]);
  const selectedDxfPreview = useMemo(() => {
    if (!selectedDxfData) {
      return {
        meshData: null,
        error: ""
      };
    }
    try {
      return {
        meshData: buildDxfPreviewMeshData(selectedDxfData, effectiveDxfThicknessMm, normalizedSelectedDxfBendSettings),
        error: ""
      };
    } catch (error) {
      return {
        meshData: null,
        error: error instanceof Error ? error.message : String(error)
      };
    }
  }, [effectiveDxfThicknessMm, normalizedSelectedDxfBendSettings, selectedDxfData]);
  const selectedDxfMeshData = selectedDxfPreview.meshData;
  const selectedDxfPreviewError = selectedDxfPreview.error;
  const selectedDxfPreviewKey = useMemo(() => {
    const baseKey = buildDxfCacheKey(selectedEntry);
    if (!baseKey || !selectedDxfData) {
      return baseKey;
    }
    const bendsKey = normalizedSelectedDxfBendSettings
      .map((setting) => `${normalizeDxfBendDirection(setting?.direction)}:${normalizeDxfBendAngleDeg(setting?.angleDeg).toFixed(1)}`)
      .join("|");
    return `${baseKey}:t=${effectiveDxfThicknessMm.toFixed(2)}:b=${bendsKey}`;
  }, [
    effectiveDxfThicknessMm,
    normalizedSelectedDxfBendSettings,
    selectedDxfData,
    selectedEntry
  ]);
  const effectiveRenderFormat = selectedEntrySourceFormat;
  const dxfViewerLoading =
    !!selectedEntry &&
    dxfStatus !== ASSET_STATUS.ERROR &&
    (!selectedDxfMatches || dxfStatus === ASSET_STATUS.LOADING);
  const gcodeViewerLoading =
    !!selectedEntry &&
    gcodeStatus !== ASSET_STATUS.ERROR &&
    (!selectedGcodeMatches || gcodeStatus === ASSET_STATUS.LOADING);
  const implicitViewerLoading =
    !!selectedEntry &&
    implicitStatus !== ASSET_STATUS.ERROR &&
    (!selectedImplicitMatches || implicitStatus === ASSET_STATUS.LOADING);
  const urdfViewerLoading =
    !!selectedEntry &&
    urdfStatus !== ASSET_STATUS.ERROR &&
    (!selectedUrdfMatches || urdfStatus === ASSET_STATUS.LOADING);
  const stepArtifactBlocksRender =
    effectiveRenderFormat === RENDER_FORMAT.STEP &&
    selectedEntry?.artifact &&
    !selectedEntry.artifact.ok &&
    !selectedEntryHasMesh &&
    !selectedStepArtifactRenderPending;
  const stepViewerLoading =
    !!selectedEntry &&
    (selectedStepArtifactRenderPending || !stepArtifactBlocksRender) &&
    status !== ASSET_STATUS.ERROR &&
    (!selectedMeshMatches || status === ASSET_STATUS.LOADING || selectedStepModuleLoading);
  const viewerLoading = effectiveRenderFormat === RENDER_FORMAT.DXF
    ? dxfViewerLoading
    : effectiveRenderFormat === RENDER_FORMAT.GCODE
      ? gcodeViewerLoading
      : effectiveRenderFormat === RENDER_FORMAT.IMPLICIT
        ? implicitViewerLoading
      : isRobotRenderFormat(effectiveRenderFormat)
        ? urdfViewerLoading
        : stepViewerLoading;
  const effectiveViewerLoading = viewerLoading || selectedGeneratorRunning || fileParamSelectionPending;
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
  const viewerLoadingLabel = selectedGeneratorRunning
    ? "Generating file..."
    : effectiveRenderFormat === RENDER_FORMAT.DXF
    ? selectedEntry && !selectedEntryHasDxf
      ? "Generating DXF preview..."
      : "Loading DXF preview..."
    : effectiveRenderFormat === RENDER_FORMAT.GCODE
      ? "Loading G-code preview..."
      : effectiveRenderFormat === RENDER_FORMAT.IMPLICIT
        ? "Loading implicit CAD..."
      : isRobotRenderFormat(effectiveRenderFormat)
        ? `Loading ${effectiveRenderFormat === RENDER_FORMAT.SDF ? "SDF" : "URDF"} robot...`
        : effectiveRenderFormat === RENDER_FORMAT.STL
          ? "Loading STL..."
          : effectiveRenderFormat === RENDER_FORMAT.THREE_MF
            ? "Loading 3MF..."
            : effectiveRenderFormat === RENDER_FORMAT.GLB
              ? "Loading GLB..."
              : stepUpdateInProgress
                ? "STEP changed. Updating/regenerating CAD..."
                : selectedStepArtifactRenderPending
                  ? "Generating STEP GLB artifact..."
                  : selectedStepModuleLoading
                    ? "Loading STEP module..."
                  : selectedEntry && !selectedEntryHasMesh
                    ? "Generating CAD assets..."
                    : "Loading CAD...";
  const viewerAlert = useMemo(() => {
    if (viewerRuntimeAlert?.blocking) {
      return viewerRuntimeAlert;
    }
    if (!selectedEntry || viewerLoading || selectedGeneratorRunning) {
      return null;
    }
    if (effectiveRenderFormat === RENDER_FORMAT.DXF) {
      return buildViewerDxfAlert(
        fileKey(selectedEntry),
        !!selectedDxfData,
        dxfStatus === ASSET_STATUS.ERROR ? dxfError : "",
        selectedDxfPreviewError
      );
    }
    if (effectiveRenderFormat === RENDER_FORMAT.GCODE) {
      return buildViewerMeshAlert(
        selectedEntry,
        !!selectedMeshData,
        gcodeStatus === ASSET_STATUS.ERROR ? gcodeError : selectedGcodePreviewError
      ) || viewerRuntimeAlert;
    }
    if (effectiveRenderFormat === RENDER_FORMAT.IMPLICIT) {
      return buildViewerImplicitAlert(
        fileKey(selectedEntry),
        !!selectedImplicitRuntimeModel,
        implicitStatus === ASSET_STATUS.ERROR ? implicitError : selectedImplicitRuntimeError
      ) || viewerRuntimeAlert;
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
      status === ASSET_STATUS.ERROR ? error : ""
    );
    return meshAlert || viewerRuntimeAlert;
  }, [
    dxfError,
    selectedDxfPreviewError,
    dxfStatus,
    effectiveRenderFormat,
    error,
    gcodeError,
    gcodeStatus,
    implicitError,
    implicitStatus,
    selectedDxfData,
    selectedEntry,
    selectedGeneratorRunning,
    selectedGcodePreviewError,
    selectedImplicitRuntimeError,
    selectedImplicitRuntimeModel,
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
  useEffect(() => {
    if (selectedEntrySourceFormat !== RENDER_FORMAT.DXF || !selectedDxfData || dxfThicknessMm > 0) {
      return;
    }
    setDxfThicknessMm(normalizeDxfPreviewThicknessMm(
      selectedDxfData.defaultThicknessMm,
      DEFAULT_DXF_PREVIEW_THICKNESS_MM
    ));
  }, [dxfThicknessMm, selectedDxfData, selectedEntrySourceFormat]);
  useEffect(() => {
    if (!selectedDxfFileRef || !selectedDxfData) {
      setDxfBendSettings([]);
      return;
    }
    setDxfBendSettings((current) => normalizeDxfBendSettings(selectedDxfData, current));
  }, [selectedDxfData, selectedDxfFileRef]);
  const focusedAssemblyTopologyActive = Boolean(isAssemblyView && focusedAssemblyNodeIds.length);
  const viewerInAssemblyMode =
    isAssemblyView &&
    !focusedAssemblyTopologyActive &&
    String(assemblyCurrentNode?.nodeType || "assembly").trim() === "assembly";
  const viewerMode = viewerInAssemblyMode ? "assembly" : "part";
  const drawModeActive = selectedEntrySourceFormat === RENDER_FORMAT.STEP && tabToolMode === TAB_TOOL_MODE.DRAW;
  const selectionCountBase = selectedPartIds.length + selectedReferenceIds.length + selectedMateIds.length;

  const selectedReferenceIdsRef = useRef(selectedReferenceIds);
  const selectedMateIdsRef = useRef(selectedMateIds);
  const selectedPartIdsRef = useRef(selectedPartIds);
  const selectedEntryBuildSnapshotRef = useRef({
    fileRef: "",
    stepHash: ""
  });
  const drawingStrokesRef = useRef(drawingStrokes);
  const drawingUndoStackRef = useRef(drawingUndoStack);
  const drawingRedoStackRef = useRef(drawingRedoStack);
  const viewerRef = useRef(null);
  const previewUiStateRef = useRef(null);
  const panelResizeStateRef = useRef(null);
  const fileSessionSaveTimerRef = useRef(0);
  const openTabsRef = useRef(openTabs);
  const activePerspectiveRef = useRef(null);
  const tabToolsResizeStateRef = useRef(null);
  const selectedFileSheetKeyRef = useRef("");
  const cadDirectorySessionBootstrappedRef = useRef(false);
  const cadRefQueryRescueUsedRef = useRef(false);
  const cadRefQueryResolvedOnceRef = useRef(false);

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
  const directorySessionThemeSlice = useMemo(
    () => createDirectorySessionThemeSlice(themeState, customThemePresets),
    [customThemePresets, themeState]
  );
  useEffect(() => {
    writeCadDirectorySessionState({
      fileViewerOpen: sidebarOpen,
      fileViewerExpandedDirectoryIds: fileViewerDirectoryStateInitialized ? fileViewerExpandedDirectoryIdList : null,
      fileViewerWidthPx: sidebarWidth,
      fileSheetOpen: tabToolsOpen,
      fileSheetWidthPx: fileSheetWidthIsCustom ? tabToolsWidth : defaultFileSheetWidth,
      theme: directorySessionThemeSlice
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
    tabToolsWidth,
    directorySessionThemeSlice
  ]);

  useEffect(() => {
    if (fileSheetWidthIsCustom) {
      return;
    }
    setTabToolsWidth(defaultFileSheetWidth);
  }, [defaultFileSheetWidth, fileSheetWidthIsCustom]);
  const desktopFileSheetOpen = isDesktop && tabToolsOpen && !!selectedFileSheetKind && !previewMode;
  const effectiveSidebarOpen = directoryNavigationAvailable && sidebarOpen && !previewMode;
  const desktopSidebarOpen = isDesktop && effectiveSidebarOpen && !previewMode;

  const setThemeMenuOpen = useCallback(() => {}, []);

  const readGlobalThemeState = useCallback(() => (
    readThemeSettingsState(readCustomThemePresets())
  ), []);

  const handleColorSchemePreferenceChange = useCallback((nextPreference) => {
    const normalizedPreference = normalizeColorSchemeId(nextPreference);
    if (!writeColorSchemePreference(normalizedPreference, { onWriteError: handlePersistenceWriteError })) {
      return;
    }
    setColorSchemePreference(normalizedPreference);
  }, [handlePersistenceWriteError]);

  const updateThemeSettings = useCallback((updater, options = {}) => {
    const persistGlobal = options.persistGlobal === true;
    const requestedPresetId = String(options.presetId || "").trim();
    if (persistGlobal && typeof updater !== "function") {
      const settings = normalizeThemeSettings(updater);
      const presetId = requestedPresetId || getAvailableThemePresetIdForSettings(settings, customThemePresets) || themePresetId || "";
      setThemeState({
        presetId,
        settings
      });
      if (presetId) {
        writeThemeSettings(settings, {
          presetId,
          customPresets: customThemePresets,
          onWriteError: handlePersistenceWriteError
        });
      }
      return;
    }

    setThemeState((current) => {
      const next = typeof updater === "function" ? updater(current.settings) : updater;
      const settings = normalizeThemeSettings(next);
      return {
        presetId: current.presetId || getAvailableThemePresetIdForSettings(settings, customThemePresets) || "",
        settings
      };
    });
  }, [customThemePresets, handlePersistenceWriteError, themePresetId]);

  const handleResetThemeSettings = useCallback(() => {
    const activeThemePreset = availableThemePresets.find((preset) => preset.id === themePresetId);
    if (!activeThemePreset) {
      setThemeState(readGlobalThemeState());
      return;
    }
    setThemeState({
      presetId: activeThemePreset.id,
      settings: normalizeThemeSettings(activeThemePreset.settings)
    });
  }, [availableThemePresets, readGlobalThemeState, themePresetId]);

  const handleSaveCustomThemePreset = useCallback((themeName) => {
    const savedTheme = saveAndActivateCustomThemePreset(themeName, themeSettings, {
      customPresets: customThemePresets,
      sourceThemeId: themePresetId,
      onWriteError: handlePersistenceWriteError
    });
    if (!savedTheme) {
      return null;
    }
    const savedPreset = savedTheme.preset;
    setCustomThemePresets(savedTheme.customPresets);
    setThemeState({
      presetId: savedPreset.id,
      settings: normalizeThemeSettings(savedPreset.settings)
    });
    return savedPreset;
  }, [customThemePresets, handlePersistenceWriteError, themePresetId, themeSettings]);

  const handleDeleteCustomThemePreset = useCallback((presetId) => {
    const normalizedPresetId = String(presetId || "").trim();
    if (!deleteCustomThemePreset(normalizedPresetId, { onWriteError: handlePersistenceWriteError })) {
      return false;
    }
    const nextCustomThemePresets = readCustomThemePresets();
    setCustomThemePresets(nextCustomThemePresets);
    setThemeState((current) => {
      if (current.presetId !== normalizedPresetId) {
        return current;
      }
      return readThemeSettingsState(nextCustomThemePresets);
    });
    return true;
  }, [handlePersistenceWriteError]);

  const handleUpdateThemePresetSettings = useCallback((presetId = themePresetId) => {
    const normalizedPresetId = String(presetId || "").trim();
    if (!normalizedPresetId) {
      return false;
    }
    if (!updateThemePresetSettings(normalizedPresetId, themeSettings, { onWriteError: handlePersistenceWriteError })) {
      return false;
    }
    const nextCustomThemePresets = readCustomThemePresets();
    setCustomThemePresets(nextCustomThemePresets);
    setThemeState(readThemeSettingsState(nextCustomThemePresets));
    return true;
  }, [handlePersistenceWriteError, themePresetId, themeSettings]);

  const handleResetThemePresetToDefault = useCallback((presetId) => {
    const normalizedPresetId = String(presetId || "").trim();
    if (!normalizedPresetId) {
      return false;
    }
    if (!resetThemePresetToDefault(normalizedPresetId, { onWriteError: handlePersistenceWriteError })) {
      return false;
    }
    const nextCustomThemePresets = readCustomThemePresets();
    setCustomThemePresets(nextCustomThemePresets);
    setThemeState((current) => (
      current.presetId === normalizedPresetId
        ? readThemeSettingsState(nextCustomThemePresets)
        : current
    ));
    return true;
  }, [handlePersistenceWriteError]);

  const handleRestoreDefaultThemePresets = useCallback(() => {
    if (!restoreDefaultThemePresets({ onWriteError: handlePersistenceWriteError })) {
      return false;
    }
    const nextCustomThemePresets = readCustomThemePresets();
    setCustomThemePresets(nextCustomThemePresets);
    setThemeState(readThemeSettingsState(nextCustomThemePresets));
    return true;
  }, [handlePersistenceWriteError]);

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
      sheetOpen: desktopFileSheetOpen,
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
    desktopFileSheetOpen,
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
    if (event.button !== 0) {
      return;
    }
    const rightSheetOpen = !previewMode && tabToolsOpen && !!selectedFileSheetKind;
    if (!isDesktop || !rightSheetOpen) {
      return;
    }

    event.preventDefault();
    setFileSheetWidthIsCustom(true);
    const nextWidth = resolveDesktopPanelWidths({
      viewportWidth: layoutViewportWidth,
      sidebarOpen: desktopSidebarOpen,
      sheetOpen: desktopFileSheetOpen,
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
    isDesktop,
    desktopFileSheetOpen,
    desktopSidebarOpen,
    layoutViewportWidth,
    previewMode,
    sidebarWidth,
    selectedFileSheetKind,
    setFileSheetWidthIsCustom,
    tabToolsOpen,
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

  const selectedFileStatusItems = useMemo(() => (
    selectedGeneratorRunning
      ? []
      : buildFileStatusItems({
        entry: selectedEntry,
        fileSheetKind: selectedFileSheetKind,
        stepSourceStatus: selectedStepSourceStatus,
        gcodeData: selectedGcodeData,
        urdfData: selectedUrdfData,
        viewerAlert,
        stepArtifactGenerationAvailable,
        stepArtifactGenerationState: selectedStepArtifactGenerationState,
        activeGenerationFiles: activeGeneratorFiles,
        viewerServerInfo
      })
  ), [
    activeGeneratorFiles,
    selectedEntry,
    selectedFileSheetKind,
    selectedGcodeData,
    selectedGeneratorRunning,
    selectedStepArtifactGenerationState,
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
    hasStepModulePanel: Boolean(
      selectedStepModuleDefinition ||
      selectedStepModuleStatus === "loading" ||
      selectedStepModuleError
    ),
    hasImplicitParameterPanel: Boolean(
      implicitStatus === ASSET_STATUS.LOADING ||
      selectedImplicitRuntimeError ||
      selectedImplicitDefinition?.parameters?.length ||
      selectedImplicitDefinition?.animations?.length
    ),
    hasFileStatus: selectedFileHasWarningOrErrorStatus,
    isSdf: selectedFileSheetKind === "sdf",
    motionEnabled: selectedFileSheetKind === "srdf" && selectedUrdfMotionEndEffectors.length > 0,
    showJoints: selectedFileSheetKind === "urdf" || selectedFileSheetKind === "srdf" || selectedFileSheetKind === "sdf"
  }), [
    implicitStatus,
    selectedImplicitDefinition,
    selectedImplicitRuntimeError,
    selectedFileSheetKind,
    selectedFileHasWarningOrErrorStatus,
    selectedStepModuleDefinition,
    selectedStepModuleError,
    selectedStepModuleStatus,
    selectedUrdfMotionEndEffectors
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

  const handleEditThemePreset = useCallback((presetId) => {
    const preset = availableThemePresets.find((candidate) => candidate.id === presetId);
    if (!preset) {
      return false;
    }

    updateThemeSettings(preset.settings, {
      persistGlobal: true,
      presetId: preset.id
    });

    if (openFileSheetSection(FILE_SHEET_SECTION_IDS.THEME_APPEARANCE)) {
      if (typeof window !== "undefined") {
        window.requestAnimationFrame(() => {
          window.requestAnimationFrame(() => {
            document
              .querySelector("[data-cad-theme-appearance-section='true']")
              ?.scrollIntoView({ block: "start", behavior: "instant" });
          });
        });
      }
    }

    return true;
  }, [
    availableThemePresets,
    openFileSheetSection,
    updateThemeSettings
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
    if (selectedFileSheetKind !== RENDER_FORMAT.IMPLICIT) {
      return;
    }
    const parametersSectionId = FILE_SHEET_SECTION_IDS.STEP_PARAMETERS;
    const graphicsSectionId = FILE_SHEET_SECTION_IDS.IMPLICIT_GRAPHICS;
    const hasParametersSection = renderedSelectedFileSheetSectionIds.includes(parametersSectionId);
    const hasGraphicsSection = renderedSelectedFileSheetSectionIds.includes(graphicsSectionId);
    if (!hasParametersSection && !hasGraphicsSection) {
      return;
    }
    setFileSheetOpenSectionIds((current) => {
      const baseSectionIds = normalizeFileSheetOpenSectionIds(
        Array.isArray(current) ? current : defaultSelectedFileSheetOpenSectionIds,
        renderedSelectedFileSheetSectionIds
      ).filter((sectionId) => sectionId !== graphicsSectionId);
      const nextSectionIds = hasParametersSection && !baseSectionIds.includes(parametersSectionId)
        ? [...baseSectionIds, parametersSectionId]
        : baseSectionIds;
      if (orderedStringListEqual(
        nextSectionIds,
        normalizeFileSheetOpenSectionIds(Array.isArray(current) ? current : defaultSelectedFileSheetOpenSectionIds, renderedSelectedFileSheetSectionIds)
      )) {
        return current;
      }
      return normalizeFileSheetOpenSectionIds(nextSectionIds, renderedSelectedFileSheetSectionIds);
    });
  }, [
    defaultSelectedFileSheetOpenSectionIds,
    renderedSelectedFileSheetSectionIds,
    selectedFileSheetKind,
    selectedKey
  ]);

  const buildActiveTabSnapshot = useCallback(() => {
    return cloneTabSnapshot({
      dxfThicknessMm,
      referenceQuery,
      selectedReferenceIds,
      selectedPartIds,
      inspectedAssemblyNodeId: "",
      expandedStepTreeNodeIds,
      stepTreeRootShowMore,
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
    dxfThicknessMm,
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
    stepTreeRootShowMore,
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
    const targetUrdfMotionState = targetFileKey && urdfMotionStateByFileRef?.[targetFileKey]
      ? urdfMotionStateByFileRef[targetFileKey]
      : {};
    const snapshotStepModuleAnimationState = stepModuleAnimationState.playing
      ? {
          ...stepModuleAnimationState,
          elapsedSec: getStepAnimationElapsed()
        }
      : stepModuleAnimationState;
    const snapshotStepModuleParameterValues = stepModuleAnimationState.playing
      ? getStepAnimationParameterValues()
      : stepModuleParameterValues;
    return createFileSessionSnapshot({
      fileKey: targetFileKey,
      entry: targetEntry,
      slices: {
        ...(entrySourceFormat(targetEntry) === RENDER_FORMAT.STEP ? { display: displaySettings } : {}),
        tab: buildActiveTabSnapshot(),
        dxf: {
          thicknessMm: dxfThicknessMm,
          bendSettings: dxfBendSettings
        },
        stepModule: {
          enabled: stepModuleEnabled,
          parameterValues: snapshotStepModuleParameterValues,
          animationState: snapshotStepModuleAnimationState
        },
        implicit: {
          parameterValues: implicitParameterValues,
          animationState: implicitAnimationState
        },
        urdf: {
          jointValues: targetUrdfJointValues,
          motionState: targetUrdfMotionState
        },
        largeFile: {
          selectableTopologyEnabled: largeFileState.selectableTopologyEnabled
        }
      }
    });
  }, [
    buildActiveTabSnapshot,
    displaySettings,
    dxfBendSettings,
    dxfThicknessMm,
    implicitAnimationState,
    implicitParameterValues,
    jointValuesByFileRef,
    largeFileState,
    selectedEntry,
    stepModuleAnimationState,
    stepModuleEnabled,
    stepModuleParameterValues,
    urdfMotionStateByFileRef
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
    const queryThemeState = readThemeSettingsStateFromAppearanceQuery(availableThemePresets);
    if (queryThemeState) {
      setThemeState(queryThemeState);
    }

    setLargeFileState(normalizeLargeFileState(sessionState?.slices?.largeFile));
    const entry = entryMap.get(normalizedKey);
    setDisplaySettings(
      entrySourceFormat(entry) === RENDER_FORMAT.STEP
        ? normalizeDisplaySettings(sessionState?.slices?.display)
        : normalizeDisplaySettings()
    );

    const dxfSlice = sessionState?.slices?.dxf || null;
    setDxfBendSettings(dxfSlice?.bendSettings || []);
    if (dxfSlice?.thicknessMm > 0) {
      setDxfThicknessMm(dxfSlice.thicknessMm);
    }

    const stepModuleSlice = sessionState?.slices?.stepModule || null;
    if (stepModuleSlice) {
      setStepModuleEnabled(stepModuleSlice.enabled !== false);
      setStepModuleParameterValues(stepModuleSlice.parameterValues || {});
      setStepModuleAnimationState({
        activeId: String(stepModuleSlice.animationState?.activeId || ""),
        playing: false,
        elapsedSec: Math.max(Number(stepModuleSlice.animationState?.elapsedSec) || 0, 0),
        speed: clampNumber(stepModuleSlice.animationState?.speed, 0.1, 5)
      });
    }

    const implicitSlice = sessionState?.slices?.implicit || null;
    if (implicitSlice) {
      setImplicitParameterValues(implicitSlice.parameterValues || {});
      const nextAnimationState = {
        activeId: String(implicitSlice.animationState?.activeId || ""),
        playing: false,
        elapsedSec: Math.max(Number(implicitSlice.animationState?.elapsedSec) || 0, 0),
        speed: clampNumber(implicitSlice.animationState?.speed, 0.1, 5)
      };
      implicitAnimationStateRef.current = nextAnimationState;
      setImplicitAnimationState(nextAnimationState);
    }

    const urdfSlice = sessionState?.slices?.urdf || null;
    if (urdfSlice) {
      setJointValuesByFileRef((current) => ({
        ...current,
        [normalizedKey]: urdfSlice.jointValues || {}
      }));
      setUrdfMotionStateByFileRef((current) => ({
        ...current,
        [normalizedKey]: urdfSlice.motionState || {}
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
      setUrdfMotionStateByFileRef((current) => {
        if (!current?.[normalizedKey]) {
          return current;
        }
        const next = { ...current };
        delete next[normalizedKey];
        return next;
      });
    }
  }, [availableThemePresets, entryMap, readEntrySessionState]);

  const handleDxfBendSettingChange = useCallback((bendIndex, patch) => {
    setDxfBendSettings((current) => {
      if (!selectedDxfData) {
        return current;
      }
      const next = normalizeDxfBendSettings(selectedDxfData, current).map((setting) => ({ ...setting }));
      if (bendIndex < 0 || bendIndex >= next.length) {
        return next;
      }
      if (Object.prototype.hasOwnProperty.call(patch || {}, "direction")) {
        next[bendIndex].direction = normalizeDxfBendDirection(patch.direction);
      }
      if (Object.prototype.hasOwnProperty.call(patch || {}, "angleDeg")) {
        next[bendIndex].angleDeg = normalizeDxfBendAngleDeg(patch.angleDeg);
      }
      return next;
    });
  }, [selectedDxfData]);

  const fileSheetSelectionKeyForTab = useCallback((key) => {
    const normalizedKey = String(key || "").trim();
    const fileSheetKind = fileSheetKindForEntry(entryMap.get(normalizedKey));
    return normalizedKey && fileSheetKind ? `${normalizedKey}:${fileSheetKind}` : "";
  }, [entryMap]);

  const applyTabRecord = useCallback((tabRecord) => {
    const nextTab = createTabRecord(tabRecord?.key || "", tabRecord || {});
    const nextPerspective = clonePerspectiveSnapshot(nextTab.camera);
    selectedFileSheetKeyRef.current = fileSheetSelectionKeyForTab(nextTab.key);
    setDxfThicknessMm(nextTab.dxfThicknessMm);
    setReferenceQuery(nextTab.referenceQuery);
    selectedReferenceIdsRef.current = nextTab.selectedReferenceIds;
    setSelectedReferenceIds(nextTab.selectedReferenceIds);
    selectedMateIdsRef.current = [];
    setSelectedMateIds([]);
    selectedPartIdsRef.current = nextTab.selectedPartIds;
    setSelectedPartIds(nextTab.selectedPartIds);
    setSelectedRenderPartIdByAssemblyPartId({});
    setSelectedWholeEntryCadRefToken("");
    setExpandedStepTreeNodeIds(nextTab.expandedStepTreeNodeIds);
    setStepTreeRootShowMore(nextTab.stepTreeRootShowMore);
    setFileSheetOpenSectionIds(nextTab.fileSheetOpenSectionIds);
    setHiddenPartIds(nextTab.hiddenPartIds);
    setIsolatedAssemblyNodeIds([]);
    setHoveredListReferenceId("");
    setHoveredModelReferenceId("");
    setHoveredMateId("");
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
  }, [fileSheetSelectionKeyForTab]);

  const resetActiveDirectory = useCallback(() => {
    selectedReferenceIdsRef.current = [];
    selectedMateIdsRef.current = [];
    selectedPartIdsRef.current = [];
    setSelectedWholeEntryCadRefToken("");
    setDxfThicknessMm(0);
    setDxfBendSettings([]);
    setReferenceQuery("");
    setSelectedReferenceIds([]);
    setSelectedMateIds([]);
    setSelectedPartIds([]);
    setSelectedRenderPartIdByAssemblyPartId({});
    setExpandedStepTreeNodeIds([]);
    setStepTreeRootShowMore(false);
    setFileSheetOpenSectionIds(null);
    setHiddenPartIds([]);
    setIsolatedAssemblyNodeIds([]);
    setDisplaySettings(normalizeDisplaySettings());
    setLargeFileState(normalizeLargeFileState(DEFAULT_LARGE_FILE_STATE));
    setHoveredListReferenceId("");
    setHoveredModelReferenceId("");
    setHoveredMateId("");
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
  }, [setTabToolsOpen]);

  useEffect(() => {
    if (directorySelectionActive && selectedKey) {
      resetActiveDirectory();
    }
  }, [resetActiveDirectory, selectedKey, directorySelectionActive]);

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
    const cachedDxfState = nextEntry ? getCachedDxfState(nextEntry) : null;
    const cachedUrdfState = nextEntry ? getCachedUrdfState(nextEntry) : null;
    const cachedImplicitState = nextEntry ? getCachedImplicitState(nextEntry) : null;
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

    if (!entryHasDxf(nextEntry)) {
      setDxfState(null);
      setDxfStatus(ASSET_STATUS.PENDING);
      setDxfError("");
    } else if (cachedDxfState) {
      setDxfState(cachedDxfState);
      setDxfStatus(ASSET_STATUS.READY);
      setDxfError("");
    }

    if (entrySourceFormat(nextEntry) !== RENDER_FORMAT.IMPLICIT) {
      setImplicitState(null);
      setImplicitStatus(ASSET_STATUS.PENDING);
      setImplicitError("");
    } else if (cachedImplicitState) {
      setImplicitState(cachedImplicitState);
      setImplicitStatus(ASSET_STATUS.READY);
      setImplicitError("");
    } else {
      setImplicitState(null);
      setImplicitStatus(ASSET_STATUS.PENDING);
      setImplicitError("");
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
    getCachedDxfState,
    getCachedImplicitState,
    getCachedMeshState,
    getCachedReferenceState,
    getCachedUrdfState,
    readEntrySessionState,
    selectedKey,
    setDxfError,
    setDxfState,
    setDxfStatus,
    setImplicitError,
    setImplicitState,
    setImplicitStatus,
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
    defaultDocumentTitle: DEFAULT_DOCUMENT_TITLE,
    selectedKey,
    entryMap,
    buildActiveTabSnapshot,
    catalogEntries,
    manifestRevision,
    defaultSidebarWidth: DEFAULT_SIDEBAR_WIDTH,
    sidebarMinWidth: DESKTOP_SIDEBAR_MIN_WIDTH,
    readCadParam,
    readCadRefQueryParams,
    setPendingCadRefQueryParams,
    activateEntryTab,
    resetActiveDirectory,
    writeCadParam,
    readEntrySessionState,
    applyEntrySessionState
  });

  useEffect(() => {
    if (stepModuleAnimationState.playing || implicitAnimationState.playing) {
      return undefined;
    }
    scheduleActiveFileSessionSave();
    return () => {
      clearFileSessionSaveTimer();
    };
  }, [
    clearFileSessionSaveTimer,
    implicitAnimationState.playing,
    scheduleActiveFileSessionSave,
    stepModuleAnimationState.playing
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
    const colorSchemeQuery = typeof window !== "undefined"
      ? window.matchMedia?.("(prefers-color-scheme: dark)")
      : null;
    if (!colorSchemeQuery) {
      return undefined;
    }

    const handleColorSchemeChange = () => {
      setSystemPrefersDark(colorSchemeQuery.matches === true);
    };
    handleColorSchemeChange();
    colorSchemeQuery.addEventListener?.("change", handleColorSchemeChange);
    return () => {
      colorSchemeQuery.removeEventListener?.("change", handleColorSchemeChange);
    };
  }, []);

  useEffect(() => {
    const documentColorSchemePreference = themeSettings.colorMode === THEME_COLOR_MODES.SYSTEM
      ? colorSchemePreference
      : themeSettings.colorMode;
    applyColorSchemeToDocument(documentColorSchemePreference, document.documentElement, {
      prefersDark: systemPrefersDark
    });
  }, [colorSchemePreference, systemPrefersDark, themeSettings.colorMode]);

  useEffect(() => {
    writeCustomThemePresets(customThemePresets, {
      onWriteError: handlePersistenceWriteError
    });
  }, [customThemePresets, handlePersistenceWriteError]);

  useEffect(() => {
    document.documentElement.dataset.glassTone = cadWorkspaceGlassTone;
    return () => {
      delete document.documentElement.dataset.glassTone;
    };
  }, [cadWorkspaceGlassTone]);

  useEffect(() => {
    const handleStorage = (event) => {
      const action = cadDirectoryStorageEventAction(event.key);
      if (action === CAD_DIRECTORY_STORAGE_EVENT_ACTION.IGNORE) {
        return;
      }
      if (action === CAD_DIRECTORY_STORAGE_EVENT_ACTION.COLOR_SCHEME) {
        setColorSchemePreference(readColorSchemePreference());
        return;
      }
      try {
        const nextCustomThemePresets = readCustomThemePresets();
        setCustomThemePresets(nextCustomThemePresets);
        setThemeState((current) => (
          current.presetId ? readThemeSettingsState(nextCustomThemePresets) : current
        ));
      } catch (error) {
        console.warn("Failed to sync theme from another tab", error);
      }
    };

    window.addEventListener("storage", handleStorage);
    return () => {
      window.removeEventListener("storage", handleStorage);
    };
  }, []);

  useEffect(() => {
    selectedReferenceIdsRef.current = selectedReferenceIds;
  }, [selectedReferenceIds]);

  useEffect(() => {
    selectedMateIdsRef.current = selectedMateIds;
  }, [selectedMateIds]);

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

  const resolvedDesktopPanelWidths = useMemo(() => resolveDesktopPanelWidths({
    viewportWidth: layoutViewportWidth,
    sidebarOpen: desktopSidebarOpen,
    sheetOpen: desktopFileSheetOpen,
    sidebarWidth,
    sheetWidth: tabToolsWidth,
    sidebarMinWidth: DESKTOP_SIDEBAR_MIN_WIDTH,
    sheetMinWidth: DESKTOP_TAB_TOOLS_MIN_WIDTH,
    sidebarMaxWidth: DESKTOP_SIDEBAR_MAX_WIDTH,
    sheetMaxWidth: DESKTOP_TAB_TOOLS_MAX_WIDTH
  }), [
    desktopFileSheetOpen,
    desktopSidebarOpen,
    layoutViewportWidth,
    sidebarWidth,
    tabToolsWidth
  ]);

  const clampSidebarWidth = useCallback((value) => {
    return resolveDesktopPanelWidths({
      viewportWidth: layoutViewportWidth,
      sidebarOpen: desktopSidebarOpen,
      sheetOpen: desktopFileSheetOpen,
      sidebarWidth: value,
      sheetWidth: tabToolsWidth,
      sidebarMinWidth: DESKTOP_SIDEBAR_MIN_WIDTH,
      sheetMinWidth: DESKTOP_TAB_TOOLS_MIN_WIDTH,
      sidebarMaxWidth: DESKTOP_SIDEBAR_MAX_WIDTH,
      sheetMaxWidth: DESKTOP_TAB_TOOLS_MAX_WIDTH
    }).sidebarWidth;
  }, [desktopFileSheetOpen, desktopSidebarOpen, layoutViewportWidth, tabToolsWidth]);

  const clampTabToolsWidth = useCallback((value) => {
    return resolveDesktopPanelWidths({
      viewportWidth: layoutViewportWidth,
      sidebarOpen: desktopSidebarOpen,
      sheetOpen: desktopFileSheetOpen,
      sidebarWidth,
      sheetWidth: value,
      sidebarMinWidth: DESKTOP_SIDEBAR_MIN_WIDTH,
      sheetMinWidth: DESKTOP_TAB_TOOLS_MIN_WIDTH,
      sidebarMaxWidth: DESKTOP_SIDEBAR_MAX_WIDTH,
      sheetMaxWidth: DESKTOP_TAB_TOOLS_MAX_WIDTH
    }).sheetWidth;
  }, [desktopFileSheetOpen, desktopSidebarOpen, layoutViewportWidth, sidebarWidth]);

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

  useEffect(() => {
    selectedStepArtifactBuildKeyRef.current = selectedStepArtifactBuildKey;
  }, [selectedStepArtifactBuildKey]);

  useEffect(() => {
    if (!selectedStepArtifactBuildKey || !selectedStepArtifactBuildFile) {
      return undefined;
    }

    if (selectedStepArtifactExternalGenerationActive) {
      return undefined;
    }

    if (
      selectedStepArtifactGenerationStatus === "ready" ||
      (
        selectedStepArtifactGenerationStatus === "error" &&
        selectedStepArtifactGenerationFailureCount >= STEP_ARTIFACT_GENERATION_FAILURE_DISPLAY_THRESHOLD
      )
    ) {
      return undefined;
    }

    if (stepArtifactGenerationRequestsRef.current.has(selectedStepArtifactBuildKey)) {
      return undefined;
    }

    const request = {
      key: selectedStepArtifactBuildKey,
      file: selectedStepArtifactBuildFile
    };
    stepArtifactGenerationRequestsRef.current.set(selectedStepArtifactBuildKey, request);
    setStatus(ASSET_STATUS.LOADING);
    setError("");

    const runGeneration = () => (
      runStepArtifactGenerationWithRetries({
        key: selectedStepArtifactBuildKey,
        file: selectedStepArtifactBuildFile,
        initialFailureCount: selectedStepArtifactGenerationFailureCount,
        generate: requestStepArtifactGeneration,
        isCurrent: () => stepArtifactGenerationRequestsRef.current.get(selectedStepArtifactBuildKey) === request,
        onState: (state) => {
          setStepArtifactGenerationStateByKey((current) => ({
            ...current,
            [selectedStepArtifactBuildKey]: state
          }));
        },
        onFinalError: (message) => {
          if (selectedStepArtifactBuildKeyRef.current === selectedStepArtifactBuildKey) {
            setStatus(ASSET_STATUS.ERROR);
            setError(message);
          }
        },
        validatePayload: (payload) => validateGeneratedStepArtifactPayload(
          payload,
          { file: selectedStepArtifactBuildFile }
        )
      })
    );

    runGeneration()
      .finally(() => {
        if (stepArtifactGenerationRequestsRef.current.get(selectedStepArtifactBuildKey) === request) {
          stepArtifactGenerationRequestsRef.current.delete(selectedStepArtifactBuildKey);
        }
      });

    return undefined;
  }, [
    selectedStepArtifactBuildFile,
    selectedStepArtifactBuildKey,
    selectedStepArtifactExternalGenerationActive,
    selectedStepArtifactGenerationFailureCount,
    selectedStepArtifactGenerationStatus,
    setError,
    setStatus
  ]);

  useEffect(() => {
    if (!selectedStepSourceStatusKey || !selectedStepSourceStatusFile) {
      setStepSourceStatusState((current) => (
        current.status === null && !current.loading
          ? current
          : {
              key: "",
              file: "",
              status: null,
              loading: false,
              error: ""
            }
      ));
      return undefined;
    }

    let cancelled = false;
    let retryTimer = 0;
    let attempts = 0;
    const controller = new AbortController();

    const loadStatus = () => {
      setStepSourceStatusState((current) => ({
        key: selectedStepSourceStatusKey,
        file: selectedStepSourceStatusFile,
        status: current.key === selectedStepSourceStatusKey ? current.status : null,
        loading: true,
        error: ""
      }));
      requestStepSourceStatus(selectedStepSourceStatusFile, { signal: controller.signal })
        .then((payload) => {
          if (cancelled || controller.signal.aborted) {
            return;
          }
          setStepSourceStatusState({
            key: selectedStepSourceStatusKey,
            file: selectedStepSourceStatusFile,
            status: payload,
            loading: false,
            error: ""
          });
          const stepStatus = String(payload?.step?.status || "").trim();
          if (
            selectedStepArtifactGenerationStatus === "ready" &&
            (stepStatus === "missing" || stepStatus === "stale") &&
            attempts < 6
          ) {
            attempts += 1;
            retryTimer = window.setTimeout(loadStatus, 1500);
          }
        })
        .catch((statusError) => {
          if (cancelled || controller.signal.aborted) {
            return;
          }
          setStepSourceStatusState({
            key: selectedStepSourceStatusKey,
            file: selectedStepSourceStatusFile,
            status: null,
            loading: false,
            error: statusError instanceof Error ? statusError.message : String(statusError)
          });
        });
    };

    loadStatus();

    return () => {
      cancelled = true;
      controller.abort();
      if (retryTimer) {
        window.clearTimeout(retryTimer);
      }
    };
  }, [
    selectedStepArtifactGenerationStatus,
    selectedStepSourceStatusFile,
    selectedStepSourceStatusKey
  ]);

  useEffect(() => {
    if (!selectedEntry) {
      cancelMeshLoad();
      return;
    }
    if (![RENDER_FORMAT.STEP, RENDER_FORMAT.STL, RENDER_FORMAT.THREE_MF, RENDER_FORMAT.GLB].includes(effectiveRenderFormat)) {
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
    effectiveRenderFormat,
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
      cancelDxfLoad();
      return;
    }
    if (effectiveRenderFormat !== RENDER_FORMAT.DXF) {
      cancelDxfLoad();
      return;
    }
    if (!selectedEntryHasDxf) {
      cancelDxfLoad();
      setDxfState(null);
      setDxfStatus(ASSET_STATUS.PENDING);
      setDxfError("");
      return;
    }
    if (selectedDxfMatches) {
      return;
    }
    loadDxfForEntry(selectedEntry).catch((err) => {
    setDxfStatus(ASSET_STATUS.ERROR);
    setDxfError(err instanceof Error ? err.message : String(err));
    });
  }, [
    cancelDxfLoad,
    effectiveRenderFormat,
    loadDxfForEntry,
    selectedDxfMatches,
    selectedEntry,
    selectedEntryHasDxf,
    setDxfError,
    setDxfState,
    setDxfStatus
  ]);

  useEffect(() => {
    if (!selectedEntry) {
      cancelGcodeLoad();
      return;
    }
    if (effectiveRenderFormat !== RENDER_FORMAT.GCODE) {
      cancelGcodeLoad();
      return;
    }
    if (!selectedEntryHasGcode) {
      cancelGcodeLoad();
      setGcodeState(null);
      setGcodeStatus(ASSET_STATUS.PENDING);
      setGcodeError("");
      return;
    }
    if (selectedGcodeMatches) {
      return;
    }
    loadGcodeForEntry(selectedEntry).catch((err) => {
      setGcodeStatus(ASSET_STATUS.ERROR);
      setGcodeError(err instanceof Error ? err.message : String(err));
    });
  }, [
    cancelGcodeLoad,
    effectiveRenderFormat,
    loadGcodeForEntry,
    selectedEntry,
    selectedEntryHasGcode,
    selectedGcodeMatches,
    setGcodeError,
    setGcodeState,
    setGcodeStatus
  ]);

  useEffect(() => {
    if (!selectedEntry) {
      cancelImplicitLoad();
      return;
    }
    if (effectiveRenderFormat !== RENDER_FORMAT.IMPLICIT) {
      cancelImplicitLoad();
      return;
    }
    if (!selectedEntryHasImplicit) {
      cancelImplicitLoad();
      setImplicitState(null);
      setImplicitStatus(ASSET_STATUS.PENDING);
      setImplicitError("");
      return;
    }
    if (selectedImplicitMatches) {
      return;
    }
    loadImplicitForEntry(selectedEntry).catch((err) => {
      setImplicitStatus(ASSET_STATUS.ERROR);
      setImplicitError(err instanceof Error ? err.message : String(err));
    });
  }, [
    cancelImplicitLoad,
    effectiveRenderFormat,
    loadImplicitForEntry,
    selectedEntry,
    selectedEntryHasImplicit,
    selectedImplicitMatches,
    setImplicitError,
    setImplicitState,
    setImplicitStatus
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

  const selectedReferencesMatch =
    !!referenceState &&
    !!selectedEntry &&
    selectedEntryHasReferences &&
    referenceState.fileRef === fileKey(selectedEntry) &&
    referenceState.referenceHash === buildReferenceCacheKey(selectedEntry);
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
    isAssemblyView;
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
  const referenceLoadingExplicitlyRequested = pendingCadRefQueryParams.length > 0 || selectedStepPartRootActive;
  const selectedTopologyDeferredByCost = Boolean(
    plainStepReferencePickingEnabled &&
    selectedTopologyLargeByCost &&
    !selectedTopologyExplicitlyEnabled &&
    !referenceLoadingExplicitlyRequested
  );
  const topLevelReferenceSelectionActive =
    pendingCadRefQueryParams.length > 0 ||
    selectedStepPartRootActive ||
    plainStepReferencePickingEnabled;
  const referenceLoadingEnabled =
    pendingCadRefQueryParams.length > 0 ||
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
    loadReferencesForEntry(selectedEntry).catch((err) => {
      setReferenceStatus(REFERENCE_STATUS.ERROR);
      setReferenceError(err instanceof Error ? err.message : String(err));
    });
  }, [
    cancelReferenceLoad,
    isAssemblyView,
    loadReferencesForEntry,
    referenceLoadingEnabled,
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

  useEffect(() => {
    if (effectiveRenderFormat !== RENDER_FORMAT.DXF || !previewMode) {
      return;
    }
    previewUiStateRef.current = null;
    setPreviewMode(false);
  }, [effectiveRenderFormat, previewMode]);

  const {
    currentReferences,
    activeReferenceMap,
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
  const isStepTopologyReference = useCallback((reference) => {
    const selectorType = String(reference?.selectorType || "").trim();
    return selectorType === "occurrence" ||
      selectorType === "shape" ||
      selectorType === "face" ||
      selectorType === "edge";
  }, []);
  const referencePartId = useCallback((reference) => {
    const explicitPartId = String(reference?.partId || "").trim();
    if (explicitPartId) {
      return explicitPartId;
    }
    return parseAssemblyPartReferenceSelectionId(reference?.id)?.partId || "";
  }, []);

  const assemblyStepTreeTopologyReferences = useMemo(() => {
    if (!isStepView || !isAssemblyView || !selectedReferencesMatch) {
      return [];
    }
    return assignStepTreeTopologyReferencePartIds(stepTreeRoot, currentReferences);
  }, [
    currentReferences,
    isAssemblyView,
    isStepView,
    selectedReferencesMatch,
    stepTreeRoot
  ]);
  const focusedAssemblyRenderPartIds = useMemo(() => {
    if (!isAssemblyView || !focusedAssemblyNodeIds.length) {
      return [];
    }
    return uniqueStringList(
      focusedAssemblyNodeIds
        .flatMap((nodeId) => renderPartIdsForAssemblySelection(nodeId))
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
    if (!isStepView) {
      return [];
    }
    if (isAssemblyView) {
      return assemblyStepTreeTopologyReferences;
    }
    return currentReferences;
  }, [
    assemblyStepTreeTopologyReferences,
    currentReferences,
    isAssemblyView,
    isStepView
  ]);
  const displayStepTreeRoot = useMemo(() => buildStepTreeRootWithTopology({
    root: stepTreeRoot,
    references: stepTreeTopologyReferences,
    fallbackPartId: isAssemblyView ? "" : STEP_MODEL_ROOT_ID
  }), [
    isAssemblyView,
    stepTreeRoot,
    stepTreeTopologyReferences
  ]);
  const stepTreeCopyReferenceMap = useMemo(
    () => buildStepTreeCopyReferenceMap(displayStepTreeRoot),
    [displayStepTreeRoot]
  );
  useEffect(() => {
    if (!stepTreeTopologyReferences.length || isAssemblyView) {
      return;
    }
    const expansionIds = collectStepTreeRevealExpansionIds(displayStepTreeRoot, STEP_MODEL_ROOT_ID, { expandSelf: true });
    if (!expansionIds.length) {
      return;
    }
    setExpandedStepTreeNodeIds((current) => (
      uniqueStringList([...current, ...expansionIds])
    ));
  }, [
    displayStepTreeRoot,
    isAssemblyView,
    stepTreeTopologyReferences
  ]);
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
    return effectiveVisibleReferences;
  }, [effectiveVisibleReferences, stepModuleTreeSelectionDisabled]);
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
  const topologySelectionActive =
    (isAssemblyView && focusedAssemblyTopologyActive) ||
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

    if (selectedGeneratorRunning) {
      return {
        loading: true,
        label: "generating",
        title: "Generator script is running"
      };
    }

    if (effectiveRenderFormat === RENDER_FORMAT.DXF && dxfViewerLoading) {
      return {
        loading: true,
        label: selectedEntryHasDxf ? (dxfLoadStage || "loading DXF") : "building",
        title: viewerLoadingLabel
      };
    }

    if (effectiveRenderFormat === RENDER_FORMAT.GCODE && gcodeViewerLoading) {
      return {
        loading: true,
        label: selectedEntryHasGcode ? (gcodeLoadStage || "loading G-code") : "building",
        title: viewerLoadingLabel
      };
    }

    if (effectiveRenderFormat === RENDER_FORMAT.IMPLICIT && implicitViewerLoading) {
      return {
        loading: true,
        label: selectedEntryHasImplicit ? (implicitLoadStage || "loading implicit CAD") : "loading",
        title: viewerLoadingLabel
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
        label: "building",
        title: viewerLoadingLabel
      };
    }

    if (effectiveRenderFormat === RENDER_FORMAT.STEP && selectedStepArtifactRenderPending) {
      return {
        loading: true,
        label: "generating GLB",
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

    if ([RENDER_FORMAT.STEP, RENDER_FORMAT.STL, RENDER_FORMAT.THREE_MF, RENDER_FORMAT.GLB].includes(effectiveRenderFormat) && stepViewerLoading) {
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
    dxfLoadStage,
    dxfViewerLoading,
    effectiveRenderFormat,
    gcodeLoadStage,
    gcodeViewerLoading,
    implicitLoadStage,
    implicitViewerLoading,
    meshLoadStage,
    meshLoadTargetFile,
    referenceLoadStage,
    referenceSelectionPending,
    referenceSelectionStatus,
    selectedEntry,
    selectedEntryHasDxf,
    selectedEntryHasGcode,
    selectedEntryHasImplicit,
    selectedEntryHasMesh,
    selectedEntryHasUrdf,
    selectedGeneratorRunning,
    selectedStepArtifactRenderPending,
    selectedStepModuleLoading,
    stepUpdateInProgress,
    stepViewerLoading,
    urdfLoadStage,
    urdfViewerLoading,
    viewerLoadingLabel
  ]);
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

  const clearUrdfMotionStatusForFile = useCallback((fileRef) => {
    if (!fileRef) {
      return;
    }
    setUrdfMotionStateByFileRef((current) => {
      const currentState = current?.[fileRef];
      if (!currentState?.statusesByEndEffector) {
        return current;
      }
      return {
        ...current,
        [fileRef]: {
          ...currentState,
          statusesByEndEffector: {}
        }
      };
    });
  }, []);

  const cancelUrdfTrajectoryPlayback = useCallback(() => {
    const playback = urdfTrajectoryPlaybackRef.current;
    playback.token += 1;
    if (playback.frameId && typeof cancelAnimationFrame === "function") {
      cancelAnimationFrame(playback.frameId);
    }
    playback.frameId = 0;
  }, []);

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

  const syncUrdfMotionTargetToJointValues = useCallback((fileRef, nextJointValues) => {
    const normalizedFileRef = String(fileRef || "").trim();
    if (
      !normalizedFileRef ||
      !selectedUrdfData ||
      !selectedUrdfMotionEndEffector ||
      !selectedUrdfMotionEndEffectorName ||
      !selectedUrdfMotionTargetFrameName ||
      !nextJointValues ||
      typeof nextJointValues !== "object"
    ) {
      return;
    }
    const currentPosition = linkOriginInFrame(
      selectedUrdfData,
      nextJointValues,
      selectedUrdfMotionEndEffector.link,
      selectedUrdfMotionTargetFrameName
    );
    if (!currentPosition) {
      return;
    }
    const normalizedTargetPosition = normalizeMotionTargetPosition(currentPosition);
    setUrdfMotionStateByFileRef((current) => {
      const currentState = current?.[normalizedFileRef] && typeof current[normalizedFileRef] === "object"
        ? current[normalizedFileRef]
        : {};
      const targetsByEndEffector = currentState.targetsByEndEffector && typeof currentState.targetsByEndEffector === "object"
        ? currentState.targetsByEndEffector
        : {};
      const statusesByEndEffector = currentState.statusesByEndEffector && typeof currentState.statusesByEndEffector === "object"
        ? { ...currentState.statusesByEndEffector }
        : {};
      delete statusesByEndEffector[selectedUrdfMotionEndEffectorName];
      return {
        ...current,
        [normalizedFileRef]: {
          ...currentState,
          targetsByEndEffector: {
            ...targetsByEndEffector,
            [selectedUrdfMotionEndEffectorName]: normalizedTargetPosition
          },
          statusesByEndEffector
        }
      };
    });
  }, [
    selectedUrdfData,
    selectedUrdfMotionEndEffector,
    selectedUrdfMotionEndEffectorName,
    selectedUrdfMotionTargetFrameName
  ]);

  const handleUrdfJointValueChange = useCallback((joint, nextValueDeg) => {
    const jointName = String(joint?.name || "").trim();
    if (!selectedUrdfFileRef || !jointName) {
      return;
    }
    cancelUrdfTrajectoryPlayback();
    const clampedValueDeg = clampJointValueDeg(joint, nextValueDeg);
    const nextJointValues = {
      ...selectedUrdfJointValues,
      [jointName]: clampedValueDeg
    };
    setJointValuesByFileRef((current) => ({
      ...current,
      [selectedUrdfFileRef]: nextJointValues
    }));
    syncUrdfMotionTargetToJointValues(selectedUrdfFileRef, nextJointValues);
    clearUrdfMotionStatusForFile(selectedUrdfFileRef);
  }, [
    cancelUrdfTrajectoryPlayback,
    clearUrdfMotionStatusForFile,
    selectedUrdfFileRef,
    selectedUrdfJointValues,
    syncUrdfMotionTargetToJointValues
  ]);
  const handleResetUrdfPose = useCallback(() => {
    if (!selectedUrdfFileRef) {
      return;
    }
    cancelUrdfTrajectoryPlayback();
    setJointValuesByFileRef((current) => {
      if (!current?.[selectedUrdfFileRef]) {
        return current;
      }
      const next = { ...current };
      delete next[selectedUrdfFileRef];
      return next;
    });
    syncUrdfMotionTargetToJointValues(selectedUrdfFileRef, defaultSelectedUrdfJointValues);
    clearUrdfMotionStatusForFile(selectedUrdfFileRef);
  }, [
    cancelUrdfTrajectoryPlayback,
    clearUrdfMotionStatusForFile,
    defaultSelectedUrdfJointValues,
    selectedUrdfFileRef,
    syncUrdfMotionTargetToJointValues
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
    setJointValuesByFileRef((current) => ({
      ...current,
      [selectedUrdfFileRef]: nextJointValues
    }));
    syncUrdfMotionTargetToJointValues(selectedUrdfFileRef, nextJointValues);
    clearUrdfMotionStatusForFile(selectedUrdfFileRef);
  }, [
    cancelUrdfTrajectoryPlayback,
    clearUrdfMotionStatusForFile,
    selectedUrdfFileRef,
    selectedUrdfJointValues,
    syncUrdfMotionTargetToJointValues
  ]);
  const handleUrdfMotionEndEffectorChange = useCallback((nextName) => {
    if (!selectedUrdfFileRef) {
      return;
    }
    const normalizedName = String(nextName || "").trim();
    startTransition(() => {
      setUrdfMotionStateByFileRef((current) => ({
        ...current,
        [selectedUrdfFileRef]: {
          ...(current?.[selectedUrdfFileRef] && typeof current[selectedUrdfFileRef] === "object"
            ? current[selectedUrdfFileRef]
            : {}),
          activeEndEffectorName: normalizedName
        }
      }));
    });
  }, [selectedUrdfFileRef]);
  const handleUrdfMoveIt2SettingChange = useCallback((key, value) => {
    if (!selectedUrdfFileRef) {
      return;
    }
    const settingKey = String(key || "").trim();
    if (!settingKey) {
      return;
    }
    startTransition(() => {
      setUrdfMotionStateByFileRef((current) => ({
        ...current,
        [selectedUrdfFileRef]: {
          ...(current?.[selectedUrdfFileRef] && typeof current[selectedUrdfFileRef] === "object"
            ? current[selectedUrdfFileRef]
            : {}),
          [settingKey]: value
        }
      }));
    });
  }, [selectedUrdfFileRef]);
  const handleUrdfMotionTargetPositionChange = useCallback((axisIndex, nextValue) => {
    if (!selectedUrdfFileRef || !selectedUrdfMotionEndEffectorName) {
      return;
    }
    const index = Number(axisIndex);
    if (!Number.isInteger(index) || index < 0 || index > 2) {
      return;
    }
    const numericValue = toFiniteNumber(nextValue, selectedUrdfMotionTargetPosition[index] ?? 0);
    startTransition(() => {
      setUrdfMotionStateByFileRef((current) => {
        const currentState = current?.[selectedUrdfFileRef] && typeof current[selectedUrdfFileRef] === "object"
          ? current[selectedUrdfFileRef]
          : {};
        const targetsByEndEffector = currentState.targetsByEndEffector && typeof currentState.targetsByEndEffector === "object"
          ? currentState.targetsByEndEffector
          : {};
        const nextTarget = normalizeMotionTargetPosition(
          targetsByEndEffector[selectedUrdfMotionEndEffectorName],
          selectedUrdfMotionTargetPosition
        );
        nextTarget[index] = numericValue;
        const statusesByEndEffector = currentState.statusesByEndEffector && typeof currentState.statusesByEndEffector === "object"
          ? { ...currentState.statusesByEndEffector }
          : {};
        delete statusesByEndEffector[selectedUrdfMotionEndEffectorName];
        return {
          ...current,
          [selectedUrdfFileRef]: {
            ...currentState,
            targetsByEndEffector: {
              ...targetsByEndEffector,
              [selectedUrdfMotionEndEffectorName]: nextTarget
            },
            statusesByEndEffector
          }
        };
      });
    });
  }, [selectedUrdfFileRef, selectedUrdfMotionEndEffectorName, selectedUrdfMotionTargetPosition]);
  const handleUseCurrentUrdfMotionPosition = useCallback(() => {
    if (!selectedUrdfFileRef || !selectedUrdfMotionEndEffectorName || !selectedUrdfMotionCurrentPosition) {
      return;
    }
    const currentPosition = normalizeMotionTargetPosition(selectedUrdfMotionCurrentPosition);
    startTransition(() => {
      setUrdfMotionStateByFileRef((current) => {
        const currentState = current?.[selectedUrdfFileRef] && typeof current[selectedUrdfFileRef] === "object"
          ? current[selectedUrdfFileRef]
          : {};
        const targetsByEndEffector = currentState.targetsByEndEffector && typeof currentState.targetsByEndEffector === "object"
          ? currentState.targetsByEndEffector
          : {};
        const statusesByEndEffector = currentState.statusesByEndEffector && typeof currentState.statusesByEndEffector === "object"
          ? { ...currentState.statusesByEndEffector }
          : {};
        delete statusesByEndEffector[selectedUrdfMotionEndEffectorName];
        return {
          ...current,
          [selectedUrdfFileRef]: {
            ...currentState,
            targetsByEndEffector: {
              ...targetsByEndEffector,
              [selectedUrdfMotionEndEffectorName]: currentPosition
            },
            statusesByEndEffector
          }
        };
      });
    });
  }, [selectedUrdfFileRef, selectedUrdfMotionCurrentPosition, selectedUrdfMotionEndEffectorName]);
  const handleApplyUrdfMotionTarget = useCallback(async (commandName = "srdf.solvePose", targetPositionOverride = selectedUrdfMotionTargetPosition) => {
    if (!selectedUrdfFileRef || !selectedUrdfData || !selectedUrdfMotionEndEffector || !selectedUrdfMotionEndEffectorName || !selectedUrdfMotionTargetFrameName) {
      return;
    }
    const requestCommandName = commandName === "srdf.planToPose" ? "srdf.planToPose" : "srdf.solvePose";
    const targetPosition = normalizeMotionTargetPosition(targetPositionOverride);
    const showMotionError = (message) => {
      const nextMessage = String(message || "Motion request failed.");
      setMotionErrorStatus("");
      if (typeof window === "undefined") {
        setMotionErrorStatus(nextMessage);
        return;
      }
      window.setTimeout(() => {
        setMotionErrorStatus(nextMessage);
      }, 0);
    };
    setMotionErrorStatus("");
    if (!selectedUrdfMotionControls?.srdf) {
      showMotionError("SRDF data is not loaded for this file.");
      return;
    }
    if (!moveit2ServerLive) {
      showMotionError("MoveIt2 server is offline.");
      return;
    }
    cancelUrdfTrajectoryPlayback();
    setUrdfMotionStateByFileRef((current) => {
      const currentState = current?.[selectedUrdfFileRef] && typeof current[selectedUrdfFileRef] === "object"
        ? current[selectedUrdfFileRef]
        : {};
      return {
        ...current,
        [selectedUrdfFileRef]: {
          ...currentState,
          solvingEndEffectorName: selectedUrdfMotionEndEffectorName
        }
      };
    });
    try {
      const payload = await requestMoveIt2Server(requestCommandName, {
        dir: catalogRootDir,
        file: selectedUrdfFileRef,
        startJointValuesByName: jointValuesByNameToNative(selectedUrdfData, selectedUrdfJointValues),
        startJointValuesByNameDeg: selectedUrdfJointValues,
        target: {
          endEffector: selectedUrdfMotionEndEffectorName,
          frame: selectedUrdfMotionTargetFrameName,
          targetLink: selectedUrdfMotionEndEffector.link,
          xyz: targetPosition
        },
        moveit2: {
          planningGroup: selectedUrdfMoveIt2Settings.planningGroup,
          endEffector: selectedUrdfMoveIt2Settings.endEffector,
          targetLink: selectedUrdfMotionEndEffector.link,
          targetFrame: selectedUrdfMoveIt2Settings.targetFrame,
          ik: {
            positionOnly: true,
            timeout: selectedUrdfMoveIt2Settings.ikTimeout,
            attempts: selectedUrdfMoveIt2Settings.ikAttempts,
            tolerance: selectedUrdfMoveIt2Settings.ikTolerance
          },
          planning: {
            pipeline: selectedUrdfMoveIt2Settings.planningPipeline,
            plannerId: selectedUrdfMoveIt2Settings.plannerId,
            planningTime: selectedUrdfMoveIt2Settings.planningTime,
            maxVelocityScalingFactor: selectedUrdfMoveIt2Settings.maxVelocityScalingFactor,
            maxAccelerationScalingFactor: selectedUrdfMoveIt2Settings.maxAccelerationScalingFactor
          }
        }
      });
      if (payload?.ok === false) {
        showMotionError(String(payload.message || "MoveIt2 server request failed."));
        return;
      }
      const trajectory = payload?.trajectory
        ? validateUrdfMotionTrajectory(selectedUrdfData, payload.trajectory)
        : null;
      const fallbackNativeJointValues = trajectory?.points?.length
        ? trajectory.points[trajectory.points.length - 1].positionsByName
        : null;
      const fallbackDisplayJointValues = trajectory?.points?.length
        ? trajectory.points[trajectory.points.length - 1].positionsByNameDeg
        : null;
      const nativeJointValues = payload?.jointValuesByName || fallbackNativeJointValues;
      const returnedJointValues = nativeJointValues
        ? validateUrdfMotionJointValues(selectedUrdfData, nativeJointValues, { native: true })
        : validateUrdfMotionJointValues(
          selectedUrdfData,
          payload?.jointValuesByNameDeg || fallbackDisplayJointValues
        );
      const nextJointValues = {
        ...selectedUrdfJointValues,
        ...returnedJointValues
      };
      const measurement = measureUrdfMotionResult(
        selectedUrdfData,
        nextJointValues,
        { ...selectedUrdfMotionEndEffector, frame: selectedUrdfMotionTargetFrameName },
        targetPosition
      );
      const tolerance = selectedUrdfMoveIt2Settings.ikTolerance;
      if (trajectory) {
        playUrdfTrajectory(selectedUrdfFileRef, selectedUrdfJointValues, trajectory, nextJointValues);
      } else {
        setJointValuesByFileRef((current) => ({
          ...current,
          [selectedUrdfFileRef]: nextJointValues
        }));
      }
      if (measurement.positionError > tolerance) {
        showMotionError("Motion applied, but FK residual is outside tolerance.");
      }
    } catch (error) {
      showMotionError(error instanceof Error ? error.message : String(error));
    } finally {
      setUrdfMotionStateByFileRef((current) => {
        const currentState = current?.[selectedUrdfFileRef] && typeof current[selectedUrdfFileRef] === "object"
          ? current[selectedUrdfFileRef]
          : {};
        if (currentState.solvingEndEffectorName !== selectedUrdfMotionEndEffectorName) {
          return current;
        }
        const nextState = { ...currentState };
        delete nextState.solvingEndEffectorName;
        return {
          ...current,
          [selectedUrdfFileRef]: nextState
        };
      });
    }
  }, [
    cancelUrdfTrajectoryPlayback,
    catalogRootDir,
    moveit2ServerLive,
    playUrdfTrajectory,
    selectedUrdfData,
    selectedUrdfFileRef,
    selectedUrdfMotionControls,
    selectedUrdfMotionEndEffector,
    selectedUrdfMotionEndEffectorName,
    selectedUrdfMotionTargetFrameName,
    selectedUrdfMotionTargetPosition,
    selectedUrdfMoveIt2Settings,
    selectedUrdfJointValues
  ]);
  const handleSolveUrdfPose = useCallback(async () => {
    await handleApplyUrdfMotionTarget("srdf.solvePose", selectedUrdfMotionTargetPosition);
  }, [
    handleApplyUrdfMotionTarget,
    selectedUrdfMotionTargetPosition
  ]);
  const handlePlanUrdfPose = useCallback(async () => {
    await handleApplyUrdfMotionTarget("srdf.planToPose", selectedUrdfMotionTargetPosition);
  }, [
    handleApplyUrdfMotionTarget,
    selectedUrdfMotionTargetPosition
  ]);
  const restoreUrdfPosePickerPerspective = useCallback((perspective) => {
    const restoredPerspective = clonePerspectiveSnapshot(perspective);
    if (!restoredPerspective) {
      return false;
    }
    viewerRef.current?.setPerspective?.(restoredPerspective, { animate: true });
    activePerspectiveRef.current = restoredPerspective;
    setViewerPerspective(restoredPerspective);
    return true;
  }, []);
  const handleBeginUrdfPosePicker = useCallback(() => {
    if (!selectedUrdfFileRef || !selectedUrdfMoveIt2ActionsEnabled) {
      return;
    }
    const originalPerspective = clonePerspectiveSnapshot(viewerRef.current?.getPerspective?.() || activePerspectiveRef.current);
    setUrdfPosePickerState({
      fileRef: selectedUrdfFileRef,
      originalPerspective
    });
  }, [selectedUrdfFileRef, selectedUrdfMoveIt2ActionsEnabled]);
  const handleCancelUrdfPosePicker = useCallback(() => {
    const originalPerspective = urdfPosePickerState.fileRef ? urdfPosePickerState.originalPerspective : null;
    setUrdfPosePickerState(emptyUrdfPosePickerState());
    restoreUrdfPosePickerPerspective(originalPerspective);
  }, [restoreUrdfPosePickerPerspective, urdfPosePickerState.fileRef, urdfPosePickerState.originalPerspective]);
  const handleToggleUrdfPosePicker = useCallback(() => {
    if (urdfPosePickerActive) {
      handleCancelUrdfPosePicker();
      return;
    }
    handleBeginUrdfPosePicker();
  }, [handleBeginUrdfPosePicker, handleCancelUrdfPosePicker, urdfPosePickerActive]);

  useEffect(() => {
    if (!urdfPosePickerActive || typeof window === "undefined") {
      return undefined;
    }
    const handleKeyDown = (event) => {
      if (event.defaultPrevented) {
        return;
      }
      if (event.key !== "Escape" && event.key !== "Esc" && event.code !== "Escape") {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      handleCancelUrdfPosePicker();
    };
    window.addEventListener("keydown", handleKeyDown, true);
    return () => {
      window.removeEventListener("keydown", handleKeyDown, true);
    };
  }, [handleCancelUrdfPosePicker, urdfPosePickerActive]);

  const commitUrdfMotionTargetPosition = useCallback((normalizedTargetPosition) => {
    if (!selectedUrdfFileRef || !selectedUrdfMotionEndEffectorName) {
      return;
    }
    setUrdfMotionStateByFileRef((current) => {
      const currentState = current?.[selectedUrdfFileRef] && typeof current[selectedUrdfFileRef] === "object"
        ? current[selectedUrdfFileRef]
        : {};
      const targetsByEndEffector = currentState.targetsByEndEffector && typeof currentState.targetsByEndEffector === "object"
        ? currentState.targetsByEndEffector
        : {};
      const statusesByEndEffector = currentState.statusesByEndEffector && typeof currentState.statusesByEndEffector === "object"
        ? { ...currentState.statusesByEndEffector }
        : {};
      delete statusesByEndEffector[selectedUrdfMotionEndEffectorName];
      return {
        ...current,
        [selectedUrdfFileRef]: {
          ...currentState,
          targetsByEndEffector: {
            ...targetsByEndEffector,
            [selectedUrdfMotionEndEffectorName]: normalizedTargetPosition
          },
          statusesByEndEffector
        }
      };
    });
  }, [selectedUrdfFileRef, selectedUrdfMotionEndEffectorName]);
  const handleUrdfPosePointPick = useCallback(async ({ point } = {}) => {
    if (!selectedUrdfFileRef || !selectedUrdfData || !selectedUrdfMotionEndEffector || !selectedUrdfMotionEndEffectorName) {
      return;
    }
    const pickedPoint = normalizePoint3(point);
    if (!pickedPoint || !selectedUrdfPosePickerState) {
      return;
    }
    const targetPosition = rootPointInFrame(
      selectedUrdfData,
      selectedUrdfJointValues,
      pickedPoint,
      selectedUrdfMotionTargetFrameName
    );
    if (!targetPosition) {
      return;
    }
    const normalizedTargetPosition = normalizeMotionTargetPosition(targetPosition);
    const originalPerspective = selectedUrdfPosePickerState.originalPerspective;
    setUrdfPosePickerState(emptyUrdfPosePickerState());
    restoreUrdfPosePickerPerspective(originalPerspective);
    commitUrdfMotionTargetPosition(normalizedTargetPosition);
    await handleApplyUrdfMotionTarget("srdf.solvePose", normalizedTargetPosition);
  }, [
    commitUrdfMotionTargetPosition,
    handleApplyUrdfMotionTarget,
    restoreUrdfPosePickerPerspective,
    selectedUrdfData,
    selectedUrdfFileRef,
    selectedUrdfMotionEndEffector,
    selectedUrdfMotionEndEffectorName,
    selectedUrdfMotionTargetFrameName,
    selectedUrdfJointValues,
    selectedUrdfPosePickerState
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
  useEffect(() => {
    if (urdfPosePickerState.fileRef && urdfPosePickerState.fileRef !== selectedUrdfFileRef) {
      const originalPerspective = urdfPosePickerState.originalPerspective;
      setUrdfPosePickerState(emptyUrdfPosePickerState());
      restoreUrdfPosePickerPerspective(originalPerspective);
    }
  }, [
    restoreUrdfPosePickerPerspective,
    selectedUrdfFileRef,
    urdfPosePickerState.fileRef,
    urdfPosePickerState.originalPerspective
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
    const selectedMatesForCopy = selectedMateIds
      .map((id) => selectedAssemblyMateMap.get(id))
      .filter(Boolean);

    return copyPayloadWithSelectedIdFallback(buildSelectionCopyPayload({
      references: [
        ...selectedReferencesForCopy,
        ...selectedPartReferencesForCopy
      ],
      parts: [],
      mates: selectedMatesForCopy,
      entry: selectedEntry
    }), {
      selectedReferenceIds,
      selectedPartIds,
      selectedMateIds,
      copyReferenceMap: stepTreeCopyReferenceMap
    });
  }, [
    assemblyPartMap,
    displayStepTreeRoot,
    effectiveActiveReferenceMap,
    selectedAssemblyMateMap,
    selectedEntry,
    selectedMateIds,
    selectedPartIds,
    selectedReferenceIds,
    stepTreeCopyReferenceMap,
    stepTreeRoot
  ]);
  const canonicalCopySelectionLines = useMemo(
    () => copySelectionPayload.lines
      .map((line) => canonicalCadRefCopyText(line))
      .filter(Boolean),
    [copySelectionPayload.lines]
  );
  const copyButtonLabel = useMemo(
    () => buildSelectionCopyButtonLabel(canonicalCopySelectionLines, { count: copySelectionPayload.copiedCount }),
    [canonicalCopySelectionLines, copySelectionPayload.copiedCount]
  );
  const cadRefQueryParamsForUrlSignature = useMemo(() => (
    selectedEntry
      ? [
          ...(selectedWholeEntryCadRefToken ? [selectedWholeEntryCadRefToken] : []),
          ...canonicalCopySelectionLines
        ].join("\n")
      : ""
  ), [canonicalCopySelectionLines, selectedEntry, selectedWholeEntryCadRefToken]);

  useEffect(() => {
    if (!pendingCadRefQueryParams.length) {
      return;
    }

    if (!selectedEntry) {
      if (explicitFileParam || !catalogHydrated || catalogRefreshing) {
        return;
      }
      if (!cadRefQueryHasKnownEntry(pendingCadRefQueryParams, catalogEntries)) {
        setPendingCadRefQueryParams((current) => Array.isArray(current) && current.length ? [] : current);
      }
      return;
    }

    const selectionRequest = collectCadRefSelectionRequest(pendingCadRefQueryParams, selectedEntry);
    if (!selectionRequest.hasMatchingToken) {
      if (!cadRefQueryHasKnownEntry(pendingCadRefQueryParams, catalogEntries)) {
        setPendingCadRefQueryParams((current) => Array.isArray(current) && current.length ? [] : current);
      }
      return;
    }

    if (selectionRequest.needsParts && !assemblyPartsLoaded) {
      return;
    }
    if (selectionRequest.needsMates && !selectedAssemblyStructureReady) {
      return;
    }
    if (selectionRequest.needsReferences && selectedEntryHasReferences && !selectedReferencesMatch) {
      return;
    }

    const resolvedSelection = resolveCadRefSelection({
      cadRefs: pendingCadRefQueryParams,
      entry: selectedEntry,
      references: visibleReferences,
      assemblyParts: assemblyNodes,
      assemblyMates: selectedAssemblyMates,
      isAssemblyView
    });

    if (!orderedStringListEqual(selectedReferenceIdsRef.current, resolvedSelection.selectedReferenceIds)) {
      selectedReferenceIdsRef.current = resolvedSelection.selectedReferenceIds;
      setSelectedReferenceIds(resolvedSelection.selectedReferenceIds);
    }
    if (!orderedStringListEqual(selectedPartIdsRef.current, resolvedSelection.selectedPartIds)) {
      selectedPartIdsRef.current = resolvedSelection.selectedPartIds;
      setSelectedPartIds(resolvedSelection.selectedPartIds);
    }
    if (!orderedStringListEqual(selectedMateIdsRef.current, resolvedSelection.selectedMateIds)) {
      selectedMateIdsRef.current = resolvedSelection.selectedMateIds;
      setSelectedMateIds(resolvedSelection.selectedMateIds);
    }
    setSelectedRenderPartIdByAssemblyPartId((current) => Object.keys(current || {}).length ? {} : current);
    const nextWholeEntryCadRefToken = resolvedSelection.hasWholeEntryToken
      ? buildCadRefToken({ cadPath: cadPathForEntry(selectedEntry) })
      : "";
    setSelectedWholeEntryCadRefToken((current) => (
      current === nextWholeEntryCadRefToken ? current : nextWholeEntryCadRefToken
    ));
    const resolvedTreeNodeIds = uniqueStringList([
      ...resolvedSelection.selectedPartIds.flatMap((id) => collectStepTreeAncestorIds(stepTreeRoot, id)),
      ...resolvedSelection.expandedAssemblyPartIds.flatMap((id) => collectStepTreeAncestorIds(stepTreeRoot, id)),
      ...resolvedSelection.expandedAssemblyPartIds
    ]);
    if (resolvedTreeNodeIds.length) {
      setExpandedStepTreeNodeIds((current) => uniqueStringList([...current, ...resolvedTreeNodeIds]));
    }
    if (resolvedTreeNodeIds.length || resolvedSelection.selectedMateIds.length) {
      openFileSheetSection(FILE_SHEET_SECTION_IDS.STEP_TREE);
    }
    setHoveredListReferenceId((current) => current ? "" : current);
    setHoveredModelReferenceId((current) => current ? "" : current);
    setHoveredListPartId((current) => current ? "" : current);
    setHoveredModelPartId((current) => current ? "" : current);
    setHoveredMateId((current) => current ? "" : current);
    setCopyStatus((current) => current ? "" : current);
    setTabToolMode((current) => current === TAB_TOOL_MODE.REFERENCES ? current : TAB_TOOL_MODE.REFERENCES);
    setPendingCadRefQueryParams((current) => Array.isArray(current) && current.length ? [] : current);
  }, [
    assemblyPartsLoaded,
    assemblyNodes,
    assemblyRootNodeId,
    catalogEntries,
    catalogHydrated,
    catalogRefreshing,
    explicitFileParam,
    isAssemblyView,
    openFileSheetSection,
    pendingCadRefQueryParams,
    selectedEntry,
    selectedEntryHasReferences,
    selectedAssemblyMates,
    selectedAssemblyStructureReady,
    selectedReferencesMatch,
    selectedMateIdsRef,
    selectedReferenceIdsRef,
    selectedPartIdsRef,
    stepTreeRoot,
    visibleReferences
  ]);

  useEffect(() => {
    if (!cadDirectorySessionBootstrappedRef.current || pendingCadRefQueryParams.length) {
      return;
    }
    if (cadRefQueryParamsForUrlSignature) {
      cadRefQueryResolvedOnceRef.current = true;
      writeCadRefQueryParams(cadRefQueryParamsForUrlSignature.split("\n"));
      return;
    }
    if (!cadRefQueryRescueUsedRef.current && !cadRefQueryParamsForUrlSignature) {
      const liveCadRefQueryParams = readCadRefQueryParams();
      const rescuedCadRefQueryParams = liveCadRefQueryParams.length
        ? liveCadRefQueryParams
        : readNavigationCadRefQueryParams();
      if (rescuedCadRefQueryParams.length) {
        if (selectedEntry) {
          cadRefQueryRescueUsedRef.current = true;
          setPendingCadRefQueryParams(rescuedCadRefQueryParams);
        }
        return;
      }
    }
    if (!cadRefQueryResolvedOnceRef.current) {
      const liveCadRefQueryParams = readCadRefQueryParams();
      const rescuedCadRefQueryParams = liveCadRefQueryParams.length
        ? liveCadRefQueryParams
        : readNavigationCadRefQueryParams();
      if (rescuedCadRefQueryParams.length) {
        if (selectedEntry) {
          setPendingCadRefQueryParams((current) => (
            orderedStringListEqual(current, rescuedCadRefQueryParams) ? current : rescuedCadRefQueryParams
          ));
        }
        return;
      }
    }
    writeCadRefQueryParams([]);
  }, [
    cadRefQueryParamsForUrlSignature,
    selectedEntry,
    pendingCadRefQueryParams,
    readCadRefQueryParams,
    readNavigationCadRefQueryParams,
    setPendingCadRefQueryParams,
    cadDirectorySessionBootstrappedRef
  ]);

  const expandStepTreeAroundNode = useCallback((nodeId, { expandSelf = false } = {}) => {
    const normalizedNodeId = String(nodeId || "").trim();
    const treeRootForExpansion = displayStepTreeRoot || stepTreeRoot;
    if (!normalizedNodeId || !treeRootForExpansion) {
      return;
    }
    const idsToExpand = collectStepTreeRevealExpansionIds(treeRootForExpansion, normalizedNodeId, { expandSelf });
    if (!idsToExpand.length) {
      return;
    }
    setExpandedStepTreeNodeIds((current) => uniqueStringList([...current, ...idsToExpand]));
  }, [displayStepTreeRoot, stepTreeRoot]);

  const revealStepTreeNode = useCallback((nodeId, { expandSelf = false, source = "viewer" } = {}) => {
    const normalizedNodeId = String(nodeId || "").trim();
    if (!normalizedNodeId || selectedFileSheetKind !== "step") {
      return;
    }
    setActiveTreeNodeScrollKey(source === "viewer" ? `${Date.now()}:${normalizedNodeId}` : "");
    openFileSheetSection(FILE_SHEET_SECTION_IDS.STEP_TREE, {
      openSheet: shouldOpenFileSheetForSelectionReveal({ isDesktop, source })
    });
    expandStepTreeAroundNode(normalizedNodeId, { expandSelf });
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
      selectedReferenceType === "shape" &&
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
    const next = !multiSelect && (selectedPartIdsRef.current.length || selectedMateIdsRef.current.length)
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
    if (!multiSelect && selectedMateIdsRef.current.length) {
      selectedMateIdsRef.current = [];
      setSelectedMateIds([]);
    }
    selectedReferenceIdsRef.current = next;
    setSelectedReferenceIds(next);
    if (next.includes(normalizedReferenceId)) {
      const selectedReferenceTreeNodeId = findStepTreeTopologyNodeIdForReference(displayStepTreeRoot, normalizedReferenceId);
      revealStepTreeNode(selectedReferenceTreeNodeId || selectedReferencePartId, { expandSelf: true, source });
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
    selectedMateIdsRef.current = [];
    setSelectedWholeEntryCadRefToken("");
    setSelectedReferenceIds([]);
    setSelectedMateIds([]);
    setCopyStatus("");
  }, []);

  const resetReferenceInteractionState = useCallback(() => {
    selectedReferenceIdsRef.current = [];
    selectedMateIdsRef.current = [];
    setSelectedWholeEntryCadRefToken("");
    setSelectedReferenceIds([]);
    setSelectedMateIds([]);
    setHoveredListReferenceId("");
    setHoveredModelReferenceId("");
    setHoveredMateId("");
    setCopyStatus("");
  }, []);

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
    const selectedMatesForCopy = selectedMateIdsRef.current
      .map((id) => selectedAssemblyMateMap.get(id))
      .filter(Boolean);
    if (
      !selectedReferencesForCopy.length &&
      !selectedPartReferencesForCopy.length &&
      !selectedMatesForCopy.length
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
      mates: selectedMatesForCopy,
      entry: selectedEntry
    }), {
      selectedReferenceIds: selectedReferenceIdsRef.current,
      selectedPartIds: selectedPartIdsRef.current,
      selectedMateIds: selectedMateIdsRef.current,
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
      await copyTextToClipboard(lines.map((line) => canonicalCadRefCopyText(line)).filter(Boolean).join("\n"));
      const copiedCount = payload.copiedCount ||
        selectedReferencesForCopy.length +
        selectedPartReferencesForCopy.length +
        selectedMatesForCopy.length -
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
    selectedAssemblyMateMap,
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
    setExpandedStepTreeNodeIds((current) => (
      current.includes(normalizedNodeId)
        ? current.filter((id) => id !== normalizedNodeId)
        : [...current, normalizedNodeId]
    ));
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
    const scopedSelectableNodeIds = source === "tree"
      ? treeSelectableAssemblyNodeIdSet
      : selectableAssemblyNodeIdSet;
    if (isAssemblyView && !scopedSelectableNodeIds.has(normalizedPartId) && !alreadySelected) {
      return selectedPartIdsRef.current;
    }
    const next = !multiSelect && (selectedReferenceIdsRef.current.length || selectedMateIdsRef.current.length)
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
    if (!multiSelect && selectedMateIdsRef.current.length) {
      selectedMateIdsRef.current = [];
      setSelectedMateIds([]);
    }
    selectedPartIdsRef.current = next;
    setSelectedPartIds(next);
    if (next.includes(normalizedPartId)) {
      revealStepTreeNode(normalizedPartId, { expandSelf: true, source });
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
    selectableAssemblyNodeIdSet,
    treeSelectableAssemblyNodeIdSet,
    stepModuleTreeSelectionDisabled,
    stepUpdateInProgress
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

  const toggleMateSelection = useCallback((mateId, { multiSelect = false } = {}) => {
    if (stepUpdateInProgress || stepModuleTreeSelectionDisabled) {
      return;
    }
    setActiveTreeNodeScrollKey("");
    const normalizedMateId = String(mateId || "").trim();
    if (!normalizedMateId || !selectedAssemblyMateMap.has(normalizedMateId)) {
      return;
    }
    const next = !multiSelect && (selectedPartIdsRef.current.length || selectedReferenceIdsRef.current.length)
      ? [normalizedMateId]
      : computeNextSelectionIds(selectedMateIdsRef.current, normalizedMateId, { multiSelect });
    if (next.length && !isDesktop) {
      setSidebarOpen(false);
    }
    setSelectedWholeEntryCadRefToken("");
    if (!multiSelect && selectedPartIdsRef.current.length) {
      selectedPartIdsRef.current = [];
      setSelectedPartIds([]);
      setSelectedRenderPartIdByAssemblyPartId({});
    }
    if (!multiSelect && selectedReferenceIdsRef.current.length) {
      selectedReferenceIdsRef.current = [];
      setSelectedReferenceIds([]);
    }
    selectedMateIdsRef.current = next;
    setSelectedMateIds(next);
    setCopyStatus("");
  }, [
    isDesktop,
    selectedAssemblyMateMap,
    stepModuleTreeSelectionDisabled,
    stepUpdateInProgress
  ]);

  const selectStepTreeMateNode = useCallback((mateId, { multiSelect = false } = {}) => {
    toggleMateSelection(mateId, { multiSelect });
  }, [toggleMateSelection]);

  const clearAssemblySelectionForFocus = useCallback(() => {
    setActiveTreeNodeScrollKey("");
    selectedPartIdsRef.current = [];
    selectedReferenceIdsRef.current = [];
    selectedMateIdsRef.current = [];
    setSelectedWholeEntryCadRefToken("");
    setSelectedPartIds([]);
    setSelectedRenderPartIdByAssemblyPartId({});
    setSelectedReferenceIds([]);
    setSelectedMateIds([]);
    setCopyStatus("");
  }, []);

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
    setIsolatedAssemblyNodeIds((current) => (current.length ? [] : current));
  }, []);

  const handleExitSingleIsolate = useCallback((nodeId) => {
    const normalizedNodeId = String(nodeId || "").trim();
    if (!normalizedNodeId) {
      handleExitIsolate();
      return;
    }
    setIsolatedAssemblyNodeIds((current) => {
      const next = current.filter((id) => String(id || "").trim() !== normalizedNodeId);
      return next.length === current.length ? current : next;
    });
  }, [handleExitIsolate]);

  const clearAssemblySelection = useCallback(() => {
    clearAssemblySelectionForFocus();
    setHoveredListPartId("");
    setHoveredModelPartId("");
    setHoveredListReferenceId("");
    setHoveredModelReferenceId("");
    setHoveredMateId("");
  }, [clearAssemblySelectionForFocus]);

  useEffect(() => {
    if (!stepModuleTreeSelectionDisabled) {
      return;
    }
    if (
      selectedPartIdsRef.current.length ||
      selectedReferenceIdsRef.current.length ||
      selectedMateIdsRef.current.length ||
      selectedWholeEntryCadRefToken
    ) {
      clearAssemblySelection();
    }
  }, [clearAssemblySelection, selectedWholeEntryCadRefToken, stepModuleTreeSelectionDisabled]);

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
      expandSelf: true,
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
        expandSelf: false,
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
    if (viewerInAssemblyMode) {
      const pickedPartId = String(referenceId || "").trim();
      if (!pickedPartId) {
        setHoveredModelReferenceId("");
        setHoveredModelPartId("");
        return;
      }
      setHoveredModelReferenceId("");
      setHoveredModelPartId(resolvePickedAssemblyPartId(pickedPartId));
      return;
    }
    const nextReferenceId = String(referenceId || "").trim();
    setHoveredModelReferenceId(nextReferenceId);
  }, [viewerInAssemblyMode, resolvePickedAssemblyPartId, stepModuleTreeSelectionDisabled]);

  const handleModelReferenceActivate = useCallback((referenceId, { multiSelect = false } = {}) => {
    if (stepUpdateInProgress || stepModuleTreeSelectionDisabled) {
      return;
    }
    const nextReferenceId = String(referenceId || "").trim();
    if (!nextReferenceId) {
      clearAssemblySelection();
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

  const handleModelReferenceContext = useCallback((referenceId, { clientX = 0, clientY = 0 } = {}) => {
    if (stepUpdateInProgress || stepModuleTreeSelectionDisabled) {
      setViewerContextMenu(null);
      return;
    }
    const pickedPartId = String(referenceId || "").trim();
    const topologyReference = effectiveActiveReferenceMap.get(pickedPartId) || null;
    if (topologyReference && (isFaceReference(topologyReference) || isEdgeReference(topologyReference))) {
      const selected = selectedReferenceIdsRef.current.includes(pickedPartId);
      const actionReferenceIds = selected
        ? uniqueStringList(
          selectedReferenceIdsRef.current
            .map((id) => String(id || "").trim())
            .filter(Boolean)
        )
        : [pickedPartId];
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
        showIsolate: false,
        showHideOther: false,
        showVisibility: false,
        showHideAll: false
      });
      return;
    }
    if (!viewerInAssemblyMode) {
      setViewerContextMenu(null);
      return;
    }
    const nodeId = resolvePickedAssemblyPartId(pickedPartId);
    if (!nodeId) {
      setViewerContextMenu(null);
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
    const selectedContextNodeIds = selected
      ? uniqueStringList(
        selectedPartIdsRef.current
          .map((id) => String(id || "").trim())
          .filter(Boolean)
      )
      : [];
    const actionNodeIds = selectedContextNodeIds.length ? selectedContextNodeIds : [nodeId];
    const expansionState = buildStepTreeExpansionMenuState({
      root: displayStepTreeRoot,
      isAssemblyView,
      expandedTreeNodeIds: expandedStepTreeNodeIds,
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
      showHideAll: true,
      hideAllDisabled: false,
      hideAllLabel: hidden ? "Reveal all instances" : "Hide all instances",
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
    expandedStepTreeNodeIds,
    focusedAssemblyNodeIds,
    effectiveActiveReferenceMap,
    hiddenPartIds,
    isAssemblyView,
    isEdgeReference,
    isFaceReference,
    renderPartIdsForAssemblySelection,
    resolvePickedAssemblyPartId,
    selectedEntry,
    stepTreeCopyReferenceMap,
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
      await copyTextToClipboard(copyText);
      setCopyStatus("Copied reference");
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "Failed to copy reference");
    }
  }, []);

  const copyStepTreeContextMenuReference = useCallback(async (id, { topology = false } = {}) => {
    const normalizedId = String(id || "").trim();
    if (!normalizedId) {
      setCopyStatus("No selector ref is available for this node");
      return;
    }
    const reference = topology
      ? stepTreeCopyReferenceMap.get(normalizedId) ||
        effectiveActiveReferenceMap.get(normalizedId) ||
        copyReferenceForRawSelectorSelection(normalizedId, "topology") ||
        null
      : null;
    const partReference = !topology
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
    selectedEntry,
    stepTreeCopyReferenceMap,
    stepTreeRoot
  ]);

  const copyStepTreeMateReference = useCallback(async (mateId) => {
    const normalizedMateId = String(mateId || "").trim();
    const mate = normalizedMateId ? selectedAssemblyMateMap.get(normalizedMateId) || null : null;
    if (!mate) {
      setCopyStatus("No selector ref is available for this mate");
      return;
    }
    const copyText = buildAssemblyMateCopyText(mate, selectedEntry);
    if (!copyText) {
      setCopyStatus("No selector ref is available for this mate");
      return;
    }
    try {
      await copyTextToClipboard(copyText);
      setCopyStatus("Copied reference");
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "Failed to copy reference");
    }
  }, [
    selectedAssemblyMateMap,
    selectedEntry
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

  const handleSelectDirectory = useCallback((dir) => {
    const normalizedDir = String(dir || "").trim();
    if (!normalizedDir) {
      return;
    }
    resetActiveDirectory();
    setQuery("");
    writeCadDirParam(normalizedDir, {
      history: "push",
      preserveFile: Boolean(directorySelectionActive && explicitFileParam)
    });
    refreshCadCatalog({ markRefreshing: true }).catch((error) => {
      if (import.meta.env.DEV) {
        console.warn("Failed to refresh CAD catalog", error);
      }
    });
    refreshCadGenerationStatus();
  }, [explicitFileParam, resetActiveDirectory, directorySelectionActive]);

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
    const normalizedMode = mode === TAB_TOOL_MODE.DRAW ? TAB_TOOL_MODE.DRAW : TAB_TOOL_MODE.REFERENCES;
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

  const handleToggleFileSheet = useCallback(() => {
    if (!selectedFileSheetKind) {
      return;
    }
    setThemeMenuOpen(false);
    setViewerAlertOpen(false);
    setTabToolsOpen((current) => {
      const nextOpen = !current;
      if (nextOpen && !isDesktop) {
        setSidebarOpen(false);
      }
      return nextOpen;
    });
  }, [isDesktop, selectedFileSheetKind, setThemeMenuOpen, setTabToolsOpen]);

  const handleDownloadFileAsset = useCallback((entry, asset = "output", assetInfo = null) => {
    const fileRef = entry ? fileKey(entry) : "";
    const assetKind = String(asset || "output").trim() || "output";
    if (!fileRef || typeof window === "undefined") {
      return;
    }
    const directDownloadUrl = String(assetInfo?.downloadUrl || "").trim();
    const downloadUrl = directDownloadUrl || downloadUrlForFileAsset(fileRef, assetKind);
    setCopyStatus("");
    setScreenshotStatus("");
    const filename = String(assetInfo?.filename || "").trim();
    try {
      const result = triggerUrlDownload(downloadUrl, { filename });
      setCopyStatus(result.message);
    } catch (downloadError) {
      setCopyStatus(downloadError instanceof Error ? downloadError.message : "Download failed");
    }
  }, []);

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
      if (kind === "link") {
        copyText = String(assetInfo?.downloadUrl || "").trim() || downloadUrlForFileAsset(
          fileRef,
          assetKind,
          typeof window === "undefined" ? viewerServerInfo?.url : window.location.href
        );
        statusLabel = "Copied link";
      } else {
        const targets = copyTargetsForFileAccessAsset(assetInfo, viewerServerInfo);
        if (kind === "relativePath") {
          copyText = targets.relativePath;
          statusLabel = "Copied relative path";
        } else {
          copyText = targets.path;
          statusLabel = "Copied path";
        }
      }

      if (!copyText) {
        throw new Error("No file reference is available to copy");
      }

      await copyTextToClipboard(copyText);
      const filename = String(assetInfo?.filename || "").trim();
      setCopyStatus(filename ? `${statusLabel} for ${filename}` : statusLabel);
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "Failed to copy file reference");
    }
  }, [viewerServerInfo]);

  const handleRevealFileAsset = useCallback(async (entry, asset = "output", assetInfo = null) => {
    const fileRef = entry ? fileKey(entry) : "";
    const assetKind = String(asset || "output").trim() || "output";
    if (!fileRef || !fileRevealAvailable || typeof window === "undefined") {
      return;
    }
    const revealUrl = openUrlForFileAsset(fileRef, assetKind);
    const busyKey = `${fileRef}:${assetKind}`;
    setCopyStatus("");
    setScreenshotStatus("");

    setFileAccessBusyKey(busyKey);
    try {
      const response = await fetch(revealUrl, {
        method: "POST",
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error(await readResponseError(
          response,
          `Failed to reveal file: ${response.status} ${response.statusText}`
        ));
      }
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "Failed to reveal file");
    } finally {
      setFileAccessBusyKey((current) => (current === busyKey ? "" : current));
    }
  }, [fileRevealAvailable]);

  const handleExportImplicitFile = useCallback(async (entry, format) => {
    const fileRef = entry ? fileKey(entry) : "";
    const exportFormat = String(format || "").trim().toLowerCase();
    if (!fileRef || !exportFormat || typeof window === "undefined") {
      return;
    }
    const busyKey = `${fileRef}:export:${exportFormat}`;
    const currentParameterValues = fileRef === selectedKey ? implicitParameterValues : null;
    const currentAnimationState = fileRef === selectedKey ? selectedImplicitAnimationViewState : null;
    setCopyStatus("");
    setScreenshotStatus("");
    setFileAccessBusyKey(busyKey);
    try {
      setCopyStatus(`Exporting ${exportFormat.toUpperCase()}...`);
      const payload = await requestImplicitCadExport({
        file: fileRef,
        format: exportFormat,
        parameterValues: currentParameterValues,
        animationState: currentAnimationState,
        resolution: DEFAULT_IMPLICIT_EXPORT_RESOLUTION,
      });
      const filename = String(payload?.filename || payload?.result?.filename || "").trim();
      const downloadUrl = String(payload?.downloadUrl || "").trim();
      if (downloadUrl) {
        const result = triggerUrlDownload(downloadUrl, { filename });
        setCopyStatus(result.message);
      } else {
        setCopyStatus(filename ? `Exported ${filename}` : `Exported ${exportFormat.toUpperCase()}`);
      }
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "Implicit CAD export failed");
    } finally {
      setFileAccessBusyKey((current) => (current === busyKey ? "" : current));
    }
  }, [
    implicitParameterValues,
    selectedImplicitAnimationViewState,
    selectedKey
  ]);

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
  }, [scheduleActiveFileSessionSave]);

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
    sidebarOpen,
    previewUiStateRef,
    tabToolMode,
    drawingUndoStackRef,
    drawingRedoStackRef,
    handleUndoDrawing,
    handleRedoDrawing,
    setPreviewMode,
    setViewerAlertOpen,
    setThemeMenuOpen,
    setTabToolsOpen,
    setSidebarOpen,
    setTabToolMode
  });

  const handleScreenshotDownload = useCallback(async () => {
    if (!selectedEntry) {
      return;
    }

    try {
      const filename = `${fileKey(selectedEntry).replace(/[^a-zA-Z0-9._-]+/g, "-")}.png`;
      if (!viewerRef.current?.captureScreenshot) {
        throw new Error("CAD Viewer not ready");
      }
      await viewerRef.current.captureScreenshot({ filename, mode: "download" });
      setCopyStatus("");
      setScreenshotStatus(`Saved ${filename}`);
    } catch (captureError) {
      setCopyStatus("");
      setScreenshotStatus(captureError instanceof Error ? captureError.message : "Screenshot capture failed");
    }
  }, [selectedEntry]);

  const handleScreenshotCopy = useCallback(async () => {
    if (!selectedEntry) {
      return;
    }

    try {
      const filename = `${fileKey(selectedEntry).replace(/[^a-zA-Z0-9._-]+/g, "-")}.png`;
      if (!viewerRef.current?.captureScreenshot) {
        throw new Error("CAD Viewer not ready");
      }
      await viewerRef.current.captureScreenshot({ filename, mode: "clipboard" });
      setCopyStatus("");
      setScreenshotStatus("Copied screenshot to clipboard");
    } catch (captureError) {
      setCopyStatus("");
      setScreenshotStatus(captureError instanceof Error ? captureError.message : "Clipboard copy failed");
    }
  }, [selectedEntry]);

  const handleEnterPreviewMode = useCallback(() => {
    const previewRenderable = effectiveRenderFormat === RENDER_FORMAT.IMPLICIT
      ? !!selectedImplicitRuntimeModel
      : !!selectedMeshData;
    if (effectiveRenderFormat === RENDER_FORMAT.DXF || viewerLoading || !previewRenderable || previewMode) {
      return;
    }
    previewUiStateRef.current = {
      sidebarOpen,
      tabToolsOpen,
      tabToolMode,
      themeMenuOpen: false,
      viewerAlertOpen
    };
    setCopyStatus("");
    setScreenshotStatus("");
    setDrawingStrokes([]);
    setDrawingUndoStack([]);
    setDrawingRedoStack([]);
    setViewerAlertOpen(false);
    setThemeMenuOpen(false);
    setSidebarOpen(false);
    setTabToolsOpen(false);
    setPreviewMode(true);
  }, [
    effectiveRenderFormat,
    previewMode,
    sidebarOpen,
    setThemeMenuOpen,
    setTabToolsOpen,
    selectedImplicitRuntimeModel,
    selectedMeshData,
    tabToolMode,
    tabToolsOpen,
    viewerAlertOpen,
    viewerLoading
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
  const selectionToolActive = effectiveRenderFormat === RENDER_FORMAT.STEP && tabToolMode === TAB_TOOL_MODE.REFERENCES;
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
  const stepTreeRootRevealNodeIds = useMemo(() => uniqueStringList([
    ...selectedPartIds,
    activeReferencePartTreeNodeId
  ]), [
    activeReferencePartTreeNodeId,
    selectedPartIds
  ]);
  useEffect(() => {
    if (!isStepView || !activeReferenceTreeNodeId || activeReferenceTreeNodeId === activeReferencePartTreeNodeId) {
      return;
    }
    expandStepTreeAroundNode(activeReferenceTreeNodeId);
  }, [
    activeReferencePartTreeNodeId,
    activeReferenceTreeNodeId,
    expandStepTreeAroundNode,
    isStepView
  ]);
  useEffect(() => {
    if (!stepTreeRoot || !isStepView) {
      return;
    }
    const rootItemCount = stepTreeNodeChildren(stepTreeRoot).length;
    if (!isAssemblyView || rootItemCount <= STEP_TREE_ROOT_ITEM_LIMIT) {
      if (stepTreeRootShowMore) {
        setStepTreeRootShowMore(false);
      }
      return;
    }
    if (stepTreeRootShowMore) {
      return;
    }
    const hiddenSelectedNodeId = stepTreeRootRevealNodeIds.find((nodeId) => (
      stepTreeRootChildIndexForNode(stepTreeRoot, nodeId) >= STEP_TREE_ROOT_ITEM_LIMIT
    ));
    if (!hiddenSelectedNodeId) {
      return;
    }
    setStepTreeRootShowMore(true);
    expandStepTreeAroundNode(hiddenSelectedNodeId, { expandSelf: true });
  }, [
    expandStepTreeAroundNode,
    isAssemblyView,
    isStepView,
    stepTreeRoot,
    stepTreeRootRevealNodeIds,
    stepTreeRootShowMore
  ]);
  const canUndoDrawing = drawingUndoStack.length > 0;
  const canRedoDrawing = drawingRedoStack.length > 0;
  const fileSheetOpen = !!selectedFileSheetKind && tabToolsOpen && !previewMode;
  const activeSidebarWidth = desktopSidebarOpen
    ? resolvedDesktopPanelWidths.sidebarWidth
    : 0;
  const activeSheetWidth = desktopFileSheetOpen
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
  const renderDisplaySettings = isStepView ? displaySettings : null;
  const selectedStepEdgeAvailability =
    selectedDisplayEdgeRuntime?.edgeRendering ||
    selectedEntry?.artifact?.edgeRendering ||
    null;
  const themeSections = (
    <>
      {isStepView ? (
        <DisplaySettingsSection
          displaySettings={displaySettings}
          updateDisplaySettings={updateDisplaySettings}
          clipBounds={selectedMeshData?.bounds || null}
          showClip
        />
      ) : null}
      <ThemeSettingsSections
        themePresets={availableThemePresets}
        themeSettings={themeSettings}
        themePresetId={themePresetId}
        resolvedColorSchemeMode={resolvedColorSchemeMode}
        updateThemeSettings={updateThemeSettings}
        handleResetThemeSettings={handleResetThemeSettings}
        handleSaveCustomThemePreset={handleSaveCustomThemePreset}
        handleUpdateThemePresetSettings={handleUpdateThemePresetSettings}
        showEdgeSettings={isStepView}
        edgeAvailability={selectedStepEdgeAvailability}
      />
    </>
  );

  return (
    <SidebarProvider
      open={effectiveSidebarOpen}
      onOpenChange={handleSidebarOpenChange}
      mobileOpen={effectiveSidebarOpen}
      onMobileOpenChange={handleSidebarOpenChange}
      data-glass-tone={cadWorkspaceGlassTone}
      style={{ "--sidebar-width": `${sidebarShellWidth}px` }}
      className="relative h-svh overflow-hidden bg-transparent"
    >
      <div className="fixed inset-0 z-0">
        <CadRenderPane
          viewerRef={viewerRef}
          renderFormat={effectiveRenderFormat}
          renderPartsIndividually={isUrdfView || Boolean(selectedStepParameterRuntime)}
          stepParameters={selectedStepParameterRuntime}
          selectedMeshData={selectedMeshData}
          selectedDxfData={selectedDxfData}
          selectedDxfMeshData={selectedDxfMeshData}
          selectedImplicitModel={selectedImplicitRuntimeModel}
          implicitDynamicRenderActive={implicitDynamicRenderActive}
          implicitGraphicsSettings={implicitGraphicsSettings}
          selectedKey={selectedKey}
          selectedDxfKey={selectedDxfPreviewKey}
          missingFileRef={missingFileRef}
          viewerPerspective={viewerPerspective}
          viewerPerspectiveRef={activePerspectiveRef}
          themeSettings={resolvedThemeSettings}
          displaySettings={renderDisplaySettings}
          previewMode={previewMode}
          viewportFrameInsets={viewportFrameInsets}
          viewerLoading={viewerLoading}
          viewerAlert={viewerAlert}
          stepUpdateInProgress={effectiveRenderFormat === RENDER_FORMAT.STEP && stepUpdateInProgress}
          referenceSelectionPending={referenceSelectionPending}
          referenceSelectionUnavailable={referenceSelectionUnavailable}
          referenceSelectionDeferred={selectedTopologyDeferredByCost}
          viewPlaneOffsetRight={viewportFrameInsets.right + 16}
          viewerMode={viewerMode}
          assemblyParts={viewerAssemblyRenderParts}
          hiddenPartIds={viewerHiddenPartIds}
          selectedPartIds={viewerSelectedPartIds}
          hoveredPartId={viewerHoveredPartIds}
          assemblyMates={selectedAssemblyMates}
          selectedMateIds={selectedMateIds}
          hoveredMateId={hoveredMateId}
          hoveredReferenceId={effectiveHoveredReferenceId}
          selectedReferenceIds={selectedReferenceIds}
          selectorRuntime={effectiveSelectorRuntime}
          displayEdgeRuntime={selectedDisplayEdgeRuntime}
          pickableFaces={viewerPickableFaces}
          pickableEdges={viewerPickableEdges}
          pickableVertices={viewerPickableVertices}
          focusedPartIds={viewerFocusedPartIds}
          drawToolActive={drawToolActive}
          drawingTool={drawingTool}
          drawingStrokes={drawingStrokes}
          handleDrawingStrokesChange={handleDrawingStrokesChange}
          handlePerspectiveChange={handlePerspectiveChange}
          handleModelHoverChange={handleModelHoverChange}
          handleModelReferenceActivate={handleModelReferenceActivate}
          handleModelReferenceDoubleActivate={handleModelReferenceDoubleActivate}
          handleModelReferenceContext={handleModelReferenceContext}
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
          onViewerContextMenuExpandSelected={expandSelectedViewerContextMenuNodes}
          onViewerContextMenuCollapseSelected={collapseSelectedViewerContextMenuNodes}
          onViewerContextMenuExpandAll={expandAllViewerContextMenuNodes}
          onViewerContextMenuCollapseAll={collapseAllViewerContextMenuNodes}
          handleViewerAlertChange={handleViewerAlertChange}
          handleStepModuleTransformDetectedChange={handleStepModuleTransformDetectedChange}
          selectionCount={selectionCount}
          copyButtonLabel={copyButtonLabel}
          handleCopySelection={handleCopySelection}
          handleScreenshotCopy={handleScreenshotCopy}
          urdfPosePicker={isUrdfView && selectedUrdfMoveIt2ActionsEnabled ? {
            active: urdfPosePickerActive,
            center: URDF_POSE_PICKER_DEFAULT_CENTER,
            onPickPoint: handleUrdfPosePointPick,
            onCancel: handleCancelUrdfPosePicker
          } : null}
        />
      </div>

      <SidebarInset className="pointer-events-none relative z-10 h-svh min-w-0 overflow-hidden bg-transparent">
        <CadWorkspaceTopBar
          previewMode={previewMode}
          sidebarLabelForEntry={sidebarLabelForEntry}
          directoryTree={allEntriesTree}
          selectedKey={selectedKey}
          selectedEntry={selectedEntry}
          onSelectEntry={handleSelectEntry}
          entrySourceFormat={entrySourceFormat}
          entryHasMesh={entryHasMesh}
          entryHasDxf={entryHasDxf}
          entryHasGcode={entryHasGcode}
          entryHasUrdf={entryHasUrdf}
          activeGenerationFiles={activeGeneratorFiles}
          activeStepArtifactGenerationFile={activeStepArtifactGenerationFiles}
          stepArtifactGenerationAvailable={stepArtifactGenerationAvailable}
          themePresets={availableThemePresets}
          themeSettings={themeSettings}
          themePresetId={themePresetId}
          resolvedColorSchemeMode={resolvedColorSchemeMode}
          onColorSchemePreferenceChange={handleColorSchemePreferenceChange}
          updateThemeSettings={updateThemeSettings}
          handleResetThemeSettings={handleResetThemeSettings}
          handleSaveCustomThemePreset={handleSaveCustomThemePreset}
          handleUpdateThemePresetSettings={handleUpdateThemePresetSettings}
          handleDeleteCustomThemePreset={handleDeleteCustomThemePreset}
          handleEditThemePreset={handleEditThemePreset}
          handleResetThemePresetToDefault={handleResetThemePresetToDefault}
          handleRestoreDefaultThemePresets={handleRestoreDefaultThemePresets}
          filenameLoadActivity={filenameLoadActivity}
          selectedStepSourceStatus={selectedStepSourceStatus}
          canRevealFileAssets={fileRevealAvailable}
          canCopyFileAssetLinks={fileLinkCopyAvailable}
          canCopyFileAssetPaths={filePathCopyAvailable}
          fileAccessBusyKey={fileAccessBusyKey}
          onDownloadFileAsset={handleDownloadFileAsset}
          onExportImplicitFile={handleExportImplicitFile}
          onRevealFileAsset={handleRevealFileAsset}
          onRevealInExplorerView={handleRevealEntryInExplorerView}
          onCopyFileAssetReference={handleCopyFileAssetReference}
          fileSheetKind={selectedFileSheetKind}
          fileSheetOpen={fileSheetOpen}
          onToggleFileSheet={handleToggleFileSheet}
          navigationAvailable={directoryNavigationAvailable}
        />

        <div className="pointer-events-none relative min-h-0 flex-1 overflow-hidden">
          <div className="flex h-full min-w-0">
            {directoryNavigationAvailable ? (
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
              entryHasGcode={entryHasGcode}
              entryHasUrdf={entryHasUrdf}
              activeGenerationFiles={activeGeneratorFiles}
              activeStepArtifactGenerationFile={activeStepArtifactGenerationFiles}
              stepArtifactGenerationAvailable={stepArtifactGenerationAvailable}
              canRevealFileAssets={fileRevealAvailable}
              canCopyFileAssetLinks={fileLinkCopyAvailable}
              canCopyFileAssetPaths={filePathCopyAvailable}
              fileAccessBusyKey={fileAccessBusyKey}
              onDownloadFileAsset={handleDownloadFileAsset}
              onExportImplicitFile={handleExportImplicitFile}
              onRevealFileAsset={handleRevealFileAsset}
              onRevealInExplorerView={handleRevealEntryInExplorerView}
              onCopyFileAssetReference={handleCopyFileAssetReference}
              catalogHydrated={catalogHydrated}
              catalogRefreshing={catalogRefreshing}
              catalogError={catalogError}
              directoryOptions={directoryOptions}
              activeDirectory={activeDirectory || explicitDirParam || ""}
              onSelectDirectory={handleSelectDirectory}
              resizable={isDesktop}
              onStartResize={handleStartSidebarResize}
            />
            ) : null}

            <div className="pointer-events-none relative min-w-0 flex-1 overflow-hidden">
              <FloatingToolBar
                previewMode={previewMode}
                selectedEntry={selectedEntry}
                renderFormat={effectiveRenderFormat}
                floatingCadToolbarPosition={floatingCadToolbarPosition}
                selectionToolActive={selectionToolActive}
                referenceSelectionPending={referenceSelectionPending}
                referenceSelectionUnavailable={referenceSelectionUnavailable}
                referenceSelectionDeferred={selectedTopologyDeferredByCost}
                urdfPosePickerAvailable={selectedUrdfMoveIt2ActionsEnabled}
                urdfPosePickerActive={urdfPosePickerActive}
                handleToggleUrdfPosePicker={handleToggleUrdfPosePicker}
                drawToolActive={drawToolActive}
                handleSelectTabToolMode={handleSelectTabToolMode}
                viewerLoading={viewerLoading}
                selectedMeshData={selectedMeshData}
                selectedDxfData={selectedDxfData}
                selectedImplicitModel={selectedImplicitRuntimeModel}
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
                handleScreenshotCopy={handleScreenshotCopy}
                handleScreenshotDownload={handleScreenshotDownload}
              />

              {!previewMode && (directorySelectionActive || (!selectedEntry && !missingFileRef && !fileParamSelectionPending)) ? (
                <CadWorkspaceHome
                  entries={catalogEntries}
                  onSelectEntry={handleSelectEntry}
                  catalogHydrated={catalogHydrated}
                  catalogRefreshing={catalogRefreshing}
                  catalogError={catalogError}
                  directorySelectionActive={directorySelectionActive}
                  directoryOptions={directoryOptions}
                  onSelectDirectory={handleSelectDirectory}
                />
              ) : null}

              <ViewerLoadingOverlay
                viewerLoading={effectiveViewerLoading}
                previewMode={previewMode}
              />
            </div>

            {selectedFileSheetKind === "dxf" ? (
              <DxfFileSheet
                key={`dxf:${selectedKey}`}
                open={fileSheetOpen}
                isDesktop={isDesktop}
                width={activeSheetWidth || tabToolsWidth}
                onOpenChange={setTabToolsOpen}
                selectedEntry={selectedEntry}
                onStartResize={handleStartFileSheetResize}
                valueMm={effectiveDxfThicknessMm}
                bendLines={selectedDxfBendLines}
                bendSettings={normalizedSelectedDxfBendSettings}
                hasDxfData={!!selectedDxfData}
                viewerLoading={viewerLoading}
                onThicknessChange={setDxfThicknessMm}
                onBendChange={handleDxfBendSettingChange}
                fileDownloadAvailable={fileLinkCopyAvailable}
                viewerServerInfo={viewerServerInfo}
                localFileOpenAvailable={fileRevealAvailable}
                fileAccessBusyKey={fileAccessBusyKey}
                onOpenFileAsset={handleRevealFileAsset}
                suppressDynamicMetadataStatus={selectedGeneratorRunning}
                statusItems={selectedFileStatusItems}
                themeSections={themeSections}
                openSectionIds={effectiveFileSheetOpenSectionIds}
                onOpenSectionIdsChange={handleFileSheetOpenSectionIdsChange}
              />
            ) : null}

            {selectedFileSheetKind === "gcode" ? (
              <GcodeFileSheet
                key={`gcode:${selectedKey}`}
                open={fileSheetOpen}
                isDesktop={isDesktop}
                width={activeSheetWidth || tabToolsWidth}
                onOpenChange={setTabToolsOpen}
                selectedEntry={selectedEntry}
                onStartResize={handleStartFileSheetResize}
                gcodeData={selectedGcodeData}
                previewMetadata={selectedGcodeMeshData?.metadata || null}
                maxLayer={selectedGcodeMaxLayer}
                showTravel={gcodeShowTravel}
                fullDetail={gcodeFullDetail}
                previewDetailLevel={gcodePreviewDetailLevel}
                onMaxLayerChange={setGcodeMaxLayer}
                onShowTravelChange={setGcodeShowTravel}
                onFullDetailChange={setGcodeFullDetail}
                onPreviewDetailLevelChange={setGcodePreviewDetailLevel}
                fileDownloadAvailable={fileLinkCopyAvailable}
                viewerServerInfo={viewerServerInfo}
                localFileOpenAvailable={fileRevealAvailable}
                fileAccessBusyKey={fileAccessBusyKey}
                onOpenFileAsset={handleRevealFileAsset}
                suppressDynamicMetadataStatus={selectedGeneratorRunning}
                statusItems={selectedFileStatusItems}
                themeSections={themeSections}
                openSectionIds={effectiveFileSheetOpenSectionIds}
                onOpenSectionIdsChange={handleFileSheetOpenSectionIdsChange}
              />
            ) : null}

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
                stepTreeRoot={displayStepTreeRoot}
                assemblyMates={selectedAssemblyMates}
                expandedTreeNodeIds={expandedStepTreeNodeIds}
                stepTreeRootShowMore={stepTreeRootShowMore}
                onStepTreeRootShowMoreChange={setStepTreeRootShowMore}
                selectedPartIds={selectedPartIds}
                selectedReferenceIds={selectedReferenceIds}
                selectedMateIds={selectedMateIds}
                selectableNodeIds={isAssemblyView ? treeSelectableAssemblyNodeIds : null}
                activeTreeNodeId={activeStepTreeNodeId}
                activeTreeNodeScrollKey={activeTreeNodeScrollKey}
                hoveredPartId={hoveredPartId}
                hoveredReferenceId={effectiveHoveredReferenceId}
                hoveredMateId={hoveredMateId}
                hiddenPartIds={hiddenPartIds}
                focusedNodeIds={focusedAssemblyNodeIds}
                onSelectTreeNode={selectStepTreeNode}
                onSelectReferenceNode={selectStepTreeReferenceNode}
                onSelectMateNode={selectStepTreeMateNode}
                onCopyTreeNodeReference={copyStepTreeContextMenuReference}
                onCopyMateNodeReference={copyStepTreeMateReference}
                onFocusTreeNode={focusStepTreeNode}
                onUnfocusTreeNode={handleExitSingleIsolate}
                onExitAllIsolate={handleExitIsolate}
                onHideOtherTreeNode={handleHideOtherTreeNode}
                onToggleTreeNode={toggleStepTreeNode}
                onClearSelection={clearAssemblySelection}
                onHoverTreeNode={setHoveredListPartId}
                onHoverReferenceNode={setHoveredListReferenceId}
                onHoverMateNode={setHoveredMateId}
                treeSelectionDisabled={stepModuleTreeSelectionDisabled}
                treeSelectionDisabledReason={stepModuleTreeSelectionDisabledReason}
                onTogglePartVisibility={togglePartVisibility}
                hideSelectedParts={handleHideSelectedParts}
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
                  animationState: selectedStepModuleAnimationViewState,
                  onParameterChange: handleStepModuleParameterChange,
                  onResetParameters: handleResetStepModuleParameters,
                  onAnimationSelect: handleStepModuleAnimationSelect,
                  onAnimationPlayToggle: handleStepModuleAnimationPlayToggle,
                  onAnimationReset: handleStepModuleAnimationReset,
                  onAnimationScrub: handleStepModuleAnimationScrub,
                  onAnimationSpeedChange: handleStepModuleAnimationSpeedChange,
                  onEnabledChange: handleStepModuleEnabledChange,
                  onCopyParams: handleCopyStepModuleParams,
                  onPasteParams: handlePasteStepModuleParams
                }}
                fileDownloadAvailable={fileLinkCopyAvailable}
                viewerServerInfo={viewerServerInfo}
                localFileOpenAvailable={fileRevealAvailable}
                fileAccessBusyKey={fileAccessBusyKey}
                onOpenFileAsset={handleRevealFileAsset}
                suppressDynamicMetadataStatus={selectedGeneratorRunning}
                statusItems={selectedFileStatusItems}
                themeSections={themeSections}
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
                groupStates={selectedUrdfGroupStates}
                activeGroupStateId={activeSelectedUrdfGroupStateId}
                jointValues={selectedUrdfJointValues}
                onJointValueChange={handleUrdfJointValueChange}
                onGroupStateSelect={handleSelectUrdfGroupState}
                onCopyJointAngles={handleCopyUrdfJointAngles}
                onResetPose={handleResetUrdfPose}
                motion={selectedFileSheetKind === "srdf" && selectedUrdfMotionControls ? {
                  srdf: selectedUrdfMotionControls.srdf,
                  endEffectors: selectedUrdfMotionEndEffectors,
                  planningGroups: selectedUrdfMotionPlanningGroups,
                  targetFrames: selectedUrdfMotionTargetFrames,
                  activeEndEffectorName: selectedUrdfMotionEndEffectorName,
                  activePlanningGroupName: selectedUrdfMoveIt2Settings.planningGroup,
                  activeTargetFrameName: selectedUrdfMoveIt2Settings.targetFrame,
                  targetPosition: selectedUrdfMotionTargetPosition,
                  currentPosition: selectedUrdfMotionCurrentPosition,
                  solving: selectedUrdfMotionSolving,
                  serverLive: moveit2ServerLive,
                  actionsEnabled: selectedUrdfMoveIt2ActionsEnabled,
                  moveit2: selectedUrdfMoveIt2Settings,
                  selectPoseActive: urdfPosePickerActive,
                  onEndEffectorChange: handleUrdfMotionEndEffectorChange,
                  onMoveIt2SettingChange: handleUrdfMoveIt2SettingChange,
                  onTargetPositionChange: handleUrdfMotionTargetPositionChange,
                  onUseCurrentPosition: handleUseCurrentUrdfMotionPosition,
                  onSolve: handleSolveUrdfPose,
                  onPlan: handlePlanUrdfPose,
                  onSelectPose: handleToggleUrdfPosePicker,
                  onCancelSelectPose: handleCancelUrdfPosePicker
                } : null}
                sdf={selectedFileSheetKind === "sdf" ? {
                  info: selectedUrdfData?.sdf || null
                } : null}
                fileDownloadAvailable={fileLinkCopyAvailable}
                viewerServerInfo={viewerServerInfo}
                localFileOpenAvailable={fileRevealAvailable}
                fileAccessBusyKey={fileAccessBusyKey}
                onOpenFileAsset={handleRevealFileAsset}
                suppressDynamicMetadataStatus={selectedGeneratorRunning}
                statusItems={selectedFileStatusItems}
                themeSections={themeSections}
                openSectionIds={effectiveFileSheetOpenSectionIds}
                onOpenSectionIdsChange={handleFileSheetOpenSectionIdsChange}
              />
            ) : null}

            {selectedFileSheetKind === "mesh" ? (
              <MeshFileSheet
                key={`mesh:${selectedKey}`}
                open={fileSheetOpen}
                title={selectedEntrySourceFormat === RENDER_FORMAT.THREE_MF ? "3MF" : selectedEntrySourceFormat === RENDER_FORMAT.GLB ? "GLB" : "STL"}
                isDesktop={isDesktop}
                width={activeSheetWidth || tabToolsWidth}
                selectedEntry={selectedEntry}
                onOpenChange={setTabToolsOpen}
                onStartResize={handleStartFileSheetResize}
                fileDownloadAvailable={fileLinkCopyAvailable}
                viewerServerInfo={viewerServerInfo}
                localFileOpenAvailable={fileRevealAvailable}
                fileAccessBusyKey={fileAccessBusyKey}
                onOpenFileAsset={handleRevealFileAsset}
                suppressDynamicMetadataStatus={selectedGeneratorRunning}
                statusItems={selectedFileStatusItems}
                themeSections={themeSections}
                openSectionIds={effectiveFileSheetOpenSectionIds}
                onOpenSectionIdsChange={handleFileSheetOpenSectionIdsChange}
              />
            ) : null}

            {selectedFileSheetKind === "implicit" ? (
              <ImplicitFileSheet
                key={`implicit:${selectedKey}`}
                open={fileSheetOpen}
                title="Implicit CAD"
                isDesktop={isDesktop}
                width={activeSheetWidth || tabToolsWidth}
                selectedEntry={selectedEntry}
                onOpenChange={setTabToolsOpen}
                onStartResize={handleStartFileSheetResize}
                parameterRuntime={{
                  status: implicitStatus === ASSET_STATUS.LOADING ? "loading" : selectedImplicitRuntimeError ? "error" : selectedImplicitDefinition ? "ready" : "idle",
                  error: selectedImplicitRuntimeError,
                  definition: selectedImplicitDefinition,
                  parameterValues: implicitParameterValues,
                  animationState: selectedImplicitAnimationViewState,
                  onParameterChange: handleImplicitParameterChange,
                  onResetParameters: handleResetImplicitParameters,
                  onAnimationSelect: handleImplicitAnimationSelect,
                  onAnimationPlayToggle: handleImplicitAnimationPlayToggle,
                  onAnimationReset: handleImplicitAnimationReset,
                  onAnimationScrub: handleImplicitAnimationScrub,
                  onAnimationSpeedChange: handleImplicitAnimationSpeedChange,
                  onCopyParams: handleCopyImplicitParams,
                  onPasteParams: handlePasteImplicitParams
                }}
                graphicsRuntime={{
                  model: selectedImplicitRuntimeModel,
                  settings: implicitGraphicsSettings,
                  onSettingsChange: updateImplicitGraphicsSettings
                }}
                fileDownloadAvailable={fileLinkCopyAvailable}
                viewerServerInfo={viewerServerInfo}
                localFileOpenAvailable={fileRevealAvailable}
                fileAccessBusyKey={fileAccessBusyKey}
                onOpenFileAsset={handleRevealFileAsset}
                suppressDynamicMetadataStatus={selectedGeneratorRunning}
                statusItems={selectedFileStatusItems}
                themeSections={themeSections}
                openSectionIds={effectiveFileSheetOpenSectionIds}
                onOpenSectionIdsChange={handleFileSheetOpenSectionIdsChange}
              />
            ) : null}
          </div>
        </div>

        <StatusToast
          copyStatus={copyStatus}
          screenshotStatus={screenshotStatus}
          persistenceStatus={persistenceStatus}
          motionErrorStatus={motionErrorStatus}
          previewMode={previewMode}
          onClear={() => {
            setCopyStatus("");
            setScreenshotStatus("");
            setPersistenceStatus("");
            setMotionErrorStatus("");
            lastPersistenceFailureKeyRef.current = "";
          }}
        />

        <ViewerAlertDialog
          viewerAlertOpen={viewerAlertOpen}
          viewerAlert={viewerAlert}
          previewMode={previewMode}
          setViewerAlertOpen={setViewerAlertOpen}
        />
      </SidebarInset>
    </SidebarProvider>
  );
}

"use client";

import { startTransition, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ArrowLeftRight, ArrowRight, Circle, Eraser, Minus, PaintBucket, PenTool, Square } from "lucide-react";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import CadRenderPane from "./workbench/CadRenderPane";
import FileViewerSidebar from "./workbench/FileViewerSidebar";
import {
  ThemeEditorPanel,
  buildDisplaySettingsTab
} from "./workbench/ThemeSettingsPopover";
import MeshFileSheet from "./workbench/MeshFileSheet";
import { DXF_PREVIEW_REFERENCE_THICKNESS_MM } from "cadjs/lib/dxf/previewGlb";
import { extractOrderedDxfBendLines } from "cadjs/lib/dxf/buildPreviewMesh";
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
import ImplicitFileSheet from "./workbench/ImplicitFileSheet";
import StepFileSheet from "./workbench/StepFileSheet";
import StatusToast from "./workbench/StatusToast";
import UrdfFileSheet from "./workbench/UrdfFileSheet";
import ViewerAlertDialog from "./workbench/ViewerAlertDialog";
import ViewerLoadingOverlay from "./workbench/ViewerLoadingOverlay";
import { formatArtifactProgress } from "@/workbench/artifactProgress.js";
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
  LIGHT_COLOR_SCHEME_ID
} from "@/ui/colorScheme";
import {
  CUSTOM_THEME_ID,
  getThemePresetIdForSettings,
  inferThemeSettingsSceneTone,
  normalizeThemeSettings,
  resolveThemeSettingsBackdropColor,
  resolveThemeSettingsForColorMode
} from "cadjs/lib/themeSettings";
import {
  displayModeForcesEdges,
  displayModeIsWireframe,
  normalizeDisplayEdgeSettings,
  normalizeDisplaySettings
} from "cadjs/lib/displaySettings";
import { clonePerspectiveSnapshot } from "cadjs/lib/perspective";
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
  fileSheetSectionIdsWithOpenSection,
  normalizeFileSheetOpenSectionIds,
  renderedFileSheetSectionIds,
  shouldOpenFileSheetForSelectionReveal
} from "@/workbench/fileSheetSections";
import {
  entryRenderAssetFormat,
  entrySourceFormat,
  fileSheetKindForEntry,
  isRobotRenderFormat
} from "cadjs/lib/fileFormats";
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
} from "cadjs/lib/renderCapabilities";
import {
  buildViewerImplicitAlert,
  buildViewerMeshAlert
} from "@/workbench/viewerAlerts";
import {
  normalizeImplicitGraphicsSettings
} from "@/workbench/implicitGraphicsSettings";
import {
  buildParameterValuesCopyText,
  parseParameterValuesPasteText
} from "@/workbench/parameterControls";
import {
  buildAssemblyMateCopyText,
  buildNormalizedReferenceState,
  buildReferenceCacheKey,
  buildSelectionCopyButtonLabel,
  buildSelectionCopyPayload,
  buildWholeStepEntryCopyReference,
  canonicalCadRefCopyText,
  computeNextSelectionIds,
  orderedStringListEqual,
  parseAssemblyPartReferenceSelectionId,
  uniqueStringList
} from "@/workbench/referenceSelection";
import {
  entryAssetHash,
  entryAssetUrl,
  entryHasDisplayEdges,
  entryHasDxf,
  entryHasImplicitCad,
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
  cadWorkspaceDefaultFileSheetWidthForViewport,
  createDirectorySessionThemeSlice,
  cloneDrawingStrokes,
  cloneTabSnapshot,
  createTabRecord,
  drawingStrokesEqual,
  readCadDirectorySessionState,
  readThemeSettingsState,
  readDirectoryThemeSettingsState,
  writeCadDirectorySessionState,
  writeThemeState,
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
  findParameterAnimation,
  hasParameterAnimations
} from "@/workbench/parameterAnimation";
import {
  buildUrdfJointAnglesCopyText,
  cloneJointValueMap,
  emptyUrdfPosePickerState,
  findBestMatchingJointValueState,
  interpolateTrajectoryJointValues,
  normalizePoint3,
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
import { buildCadRefToken } from "cadjs/lib/cadRefs.js";
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
import {
  advanceUrdfJointValues,
  interpolateUrdfJointValues,
  jointValueMapsClose,
  URDF_JOINT_ANIMATION_DURATION_MS,
  URDF_JOINT_ANIMATION_EPSILON,
  URDF_JOINT_ANIMATION_FOLLOW_MS
} from "cadjs/lib/urdf/jointAnimation";
import { checkMoveIt2ServerLive, moveit2ServerEnabled, requestMoveIt2Server } from "cadjs/lib/urdf/moveit2ServerClient";
import { readActiveCadDir } from "../workbench/cadManifestStore.js";
import {
  FILE_STATUS_LEVELS,
  buildFileStatusItems,
  fileStatusHasWarningsOrErrors,
  mostIntenseFileStatusLevel
} from "@/workbench/fileStatusItems";
import { useArtifact } from "./workbench/hooks/useArtifact.js";
import {
  rootAssemblyInspectionNodeId,
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
} from "cadjs/lib/step/stepTree";
import {
  loadStepModuleDefinition,
  normalizeStepModuleParameterValues
} from "cadjs/common/stepModule";
import {
  normalizeParameterValue,
  normalizeParameterValues
} from "cadjs/implicit/parameters";
import { copyTextToClipboard, readTextFromClipboard } from "@/ui/clipboard";
import { triggerUrlDownload } from "@/ui/download";
import {
  copyTargetsForFileAccessAsset,
  downloadUrlForFileAsset,
  openUrlForFileAsset
} from "@/workbench/fileAccessAssets";
import {
  requestModelExport,
  exportFormatLabel
} from "@/workbench/modelExport";

const DEFAULT_DOCUMENT_TITLE = "CAD Viewer";
// The source formats whose renderable geometry lives in a `__cadgen__` render package, and
// therefore go through the /__cad/artifact state machine before they can render. Mirrors
// `owns_entry` in viewer/server_py/artifact.py; an entry listed here and not there (or the
// reverse) is a format that either never builds or reports ready forever.
// Which formats build a package before they can render is a capability
// (`artifactManaged`), declared once and mirrored against the server's `owns_entry`.
// File-sheet kinds that render nothing but a status tab. A mesh never had file-specific
// controls; DXF lost its when the geometry moved into a baked render package, whose
// settings the producer owns. Implicits are NOT here -- they raymarch, so their params,
// animations and graphics settings are live controls again.
const STATUS_ONLY_FILE_SHEET_KINDS = Object.freeze(["mesh", "dxf"]);

function statusOnlyFileSheetTitle(sourceFormat) {
  return renderFormatLabel(sourceFormat) || "STL";
}

// The render-ASSET formats that come out of the shared mesh loader. Read against
// `entryRenderAssetFormat`, never the source format: a DXF entry reports GLB here because its
// geometry is the drawing package's baked preview.glb. STEP stays on the list under its own
// name -- it is mesh-loaded too, but `entryRenderAssetFormat` reports `step` for it because
// only DXF and implicit are the package-baked kinds.

// Single user-facing label for "the viewer is (re)generating the render artifacts a STEP model
// needs before it can render" — used for both the filename status chip and its tooltip across every
// artifact-generation trigger (first build, stale rebuild, source-changed regen). Browser-side
// asset-load/parse stages ("loading mesh", reference "loading topology", etc.) are a different
// concept and keep their own wording.
// The URDF loader reports its stage in lower case ("loading meshes 7/13") because the
// file-list chip reads that way; the viewport card is a sentence and needs a capital.
function capitalizeFirst(value) {
  const text = String(value || "").trim();
  return text ? `${text.slice(0, 1).toUpperCase()}${text.slice(1)}` : "";
}

const ARTIFACT_GENERATING_LABEL = "Generating artifacts";
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
// result is Object.is-equal to what it already has. The implicit animation
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
  // The baked mesh of a DXF or implicit entry is published as a `glb` relation rather than
  // as the entry's own url, so stripping only the url would leave the previous bake
  // renderable while its replacement is being built -- which is exactly the stale cache this
  // function exists to hide.
  if (next.relations?.glb) {
    const relations = { ...next.relations };
    delete relations.glb;
    next.relations = relations;
  }
  return next;
}

export default function CadWorkspace({
  manifestEntries: manifestEntriesProp = [],
  manifestRevision = 0,
  catalogHydrated = false,
  catalogRefreshing = false,
  catalogError = "",
  activeDir = ""
}) {
  const manifestEntries = Array.isArray(manifestEntriesProp) ? manifestEntriesProp : [];
  const catalogEntries = manifestEntries;
  const explicitFileParam = readCadParam();
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
  const [selectedKey, setSelectedKey] = useState("");
  const [fileSheetOpenSectionIds, setFileSheetOpenSectionIds] = useState(null);
  const [dxfThicknessMm, setDxfThicknessMm] = useState(0);
  const [dxfBendSettings, setDxfBendSettings] = useState([]);
  const [dxfViewMode, setDxfViewMode] = useState("2d");
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
  const [hiddenPartIds, setHiddenPartIds] = useState([]);
  const [isolatedAssemblyNodeIds, setIsolatedAssemblyNodeIds] = useState([]);
  const [viewerContextMenu, setViewerContextMenu] = useState(null);
  const [displaySettings, setDisplaySettings] = useState(() => normalizeDisplaySettings());
  const [hoveredListPartId, setHoveredListPartId] = useState("");
  const [hoveredModelPartId, setHoveredModelPartId] = useState("");
  const [copyStatus, setCopyStatus] = useState("");
  const [stepUpdateInProgress, setStepUpdateInProgress] = useState(false);
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
  // One active theme id plus at most one custom settings blob. Presets are
  // read-only; editing anything moves the active theme to "custom".
  const [themeState, setThemeState] = useState(() => readDirectoryThemeSettingsState());
  const themeSettings = themeState.settings;
  const themeId = themeState.themeId;
  const [themeEditing, setThemeEditing] = useState(false);
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
    () => resolveThemeSettingsForColorMode(themeSettings, { prefersDark: false }),
    [themeSettings]
  );
  const resolvedDisplayEdgeSettings = useMemo(() => {
    // Edge theme — colour, opacity, thickness — is fixed, not a user
    // setting. It comes from the cadjs defaults, or from a theme that styles its
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
  // App light/dark is inferred from the active theme's dominant background color
  // (not a user preference). The nav/sidebars float over the transparent
  // viewport, so their contrast must track whatever canvas sits behind them.
  const cadWorkspaceGlassTone = useMemo(() => inferThemeSettingsSceneTone(resolvedThemeSettings), [resolvedThemeSettings]);
  const resolvedColorSchemeMode = cadWorkspaceGlassTone === "dark"
    ? DARK_COLOR_SCHEME_ID
    : LIGHT_COLOR_SCHEME_ID;
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
  const [selectedUrdfGroupStateIdByFileRef, setSelectedUrdfGroupStateIdByFileRef] = useState({});
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
    speed: 1,
    loopEnabled: true
  });
  const stepModuleParameterValuesRef = useRef(stepModuleParameterValues);
  const stepModuleAnimationStateRef = useRef(stepModuleAnimationState);
  const [implicitParameterValues, setImplicitParameterValues] = useState({});
  const [implicitAnimationState, setImplicitAnimationState] = useState({
    activeId: "",
    playing: false,
    elapsedSec: 0,
    speed: 1,
    loopEnabled: true
  });
  const implicitAnimationStateRef = useRef(implicitAnimationState);
  const [implicitGraphicsSettings, setImplicitGraphicsSettings] = useState(() => normalizeImplicitGraphicsSettings());
  const [implicitParameterInteractionActive, setImplicitParameterInteractionActive] = useState(false);
  const implicitParameterInteractionTimerRef = useRef(0);
  const [urdfPosePickerState, setUrdfPosePickerState] = useState(emptyUrdfPosePickerState);
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
    meshLoadInProgress,
    meshLoadTargetFile,
    meshLoadStage,
    status,
    setStatus,
    error,
    setError,
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
    getCachedImplicitState,
    getCachedUrdfState,
    cancelMeshLoad,
    cancelImplicitLoad,
    cancelUrdfLoad,
    cancelReferenceLoad,
    cancelDisplayEdgeLoad,
    loadMeshForEntry,
    loadImplicitForEntry,
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
  // Unified render-artifact status for the selected entry: ready (render) | generating (loading) |
  // error (fatal). A missing/stale cache is not an issue — it just triggers a (re)build. Replaces
  // the per-entry step-source-status fetch, the mesh-stripping merge, and the build effect.
  // Every artifact-managed kind: STEP models, DXF drawings (generated `.dxf.py` AND imported
  // `.dxf` alike) and `.implicit.js` models. An imported `.dxf` used to be excluded because it
  // "renders directly from disk" -- true only while the client still parsed and extruded DXF
  // entities in the browser. It renders from the package's baked preview.glb now, so it needs
  // the build for exactly the reason a generated one does.
  const selectedArtifact = useArtifact(
    catalogSelectedEntry ? fileKey(catalogSelectedEntry) : "",
    {
      enabled: isArtifactManagedFormat(catalogSelectedEntrySourceFormat),
      freshnessKey: `${catalogSelectedEntry?.hash || ""}:${manifestRevision}`,
    }
  );
  const selectedArtifactGenerating = selectedArtifact.status === "generating";
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
  const selectedEntry = useMemo(
    () => (!catalogSelectedEntry || selectedArtifact.status === "ready"
      ? catalogSelectedEntry
      : entryWithoutRenderAssets(catalogSelectedEntry)),
    [catalogSelectedEntry, selectedArtifact.status]
  );
  // Cache states never become user-facing "issues"; only a fatal build/source failure does.
  const selectedStepSourceStatus = selectedArtifact.status === "error"
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
  // What the viewport LOADS, which is not what the user opened: a DXF's geometry is its
  // package's baked preview.glb. Gating the mesh load on the source format instead is what
  // left a built DXF spinning -- the asset was on disk and nothing ever asked for it.
  //
  // Not the whole answer, though. Two source kinds are rendered by something other than the
  // mesh loader and must not take this path even though a mesh EXISTS for them: an implicit
  // is raymarched from its module (its baked GLB is for export), and a robot is assembled
  // from per-link meshes by the URDF loader. Both would otherwise download a second copy of
  // the model and put it in the scene alongside the real one.
  const selectedEntryRendersItsOwnGeometry =
    assetKindForRenderFormat(selectedEntrySourceFormat) !== ASSET_KIND.MESH &&
    assetKindForRenderFormat(selectedEntrySourceFormat) !== ASSET_KIND.DRAWING;
  const selectedEntryRenderAssetFormat = selectedEntryRendersItsOwnGeometry
    ? selectedEntrySourceFormat
    : entryRenderAssetFormat(selectedEntry);
  const selectedFileSheetKind = fileSheetKindForEntry(selectedEntry);
  // Some kinds (e.g. a mesh/STL) have no file-specific sections; when so, hide
  // the file-sheet toggle and the sheet entirely instead of showing an empty
  // sidebar.
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
  const fileRevealAvailable = fileAccessBackend === "local-fs";
  const filePathCopyAvailable = fileAccessBackend === "local-fs" && Boolean(
    viewerServerInfo?.rootPath || viewerServerInfo?.directoryRoot
  );
  // The local-fs viewer has no remote asset links; the copy-link affordance is hosted-only.
  const fileLinkCopyAvailable = false;
  // `isStepView` used to stand in for all four of these at once, which is why adding a
  // format meant auditing every one of its ~15 uses to work out which sense was meant.
  // They are separate capabilities; today only STEP declares them, and that is a fact
  // about the table rather than about this file.
  const selectedEntryContentKind = viewportContentKind(selectedEntrySourceFormat);
  const supportsParts = hasCapability(selectedEntrySourceFormat, "parts");
  const supportsTopology = hasCapability(selectedEntrySourceFormat, "topology");
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
  const selectedStepModuleUrl = supportsSidecarParams ? entryStepModuleUrl(selectedEntry) : "";
  const selectedStepModuleCadPath = selectedStepModuleUrl ? cadPathForEntry(selectedEntry) : "";
  const selectedStepModuleDefinition = stepModuleLoadState.url === selectedStepModuleUrl
    ? stepModuleLoadState.definition
    : null;
  const selectedStepModuleHasAnimations = hasParameterAnimations(selectedStepModuleDefinition);
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
  const selectedEntryHasImplicit = entryHasImplicitCad(selectedEntry);
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
  // The loaded .implicit.js module for the selected entry. The raymarch renderer takes the
  // model straight from here -- there is no baked package in this path -- and the file
  // sheet's parameter/animation controls read the definition off it.
  const selectedImplicitModel = selectedImplicitMatches ? implicitState.model : null;
  const selectedImplicitDefinition = selectedImplicitModel?.definition || null;
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
  const selectedStepModuleActiveAnimation = useMemo(
    () => findStepModuleAnimation(selectedStepModuleDefinition, stepModuleAnimationState.activeId),
    [selectedStepModuleDefinition, stepModuleAnimationState.activeId]
  );
  const selectedStepModuleAnimationViewState = useMemo(() => ({
    ...stepModuleAnimationState,
    activeId: selectedStepModuleActiveAnimation?.id || stepModuleAnimationState.activeId || "",
    duration: selectedStepModuleActiveAnimation?.duration || 0,
    loop: selectedStepModuleActiveAnimation?.loop !== false,
    loopEnabled: stepModuleAnimationState.loopEnabled ?? (selectedStepModuleActiveAnimation?.loop !== false)
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
      elapsedSec: 0,
      // Reset the loop preference to the newly-selected animation's default.
      loopEnabled: animation?.loop !== false
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

  const handleStepModuleAnimationLoopToggle = useCallback((nextLoopEnabled) => {
    const currentState = stepModuleAnimationStateRef.current;
    const animation = findStepModuleAnimation(selectedStepModuleDefinition, currentState.activeId);
    const currentLoop = currentState.loopEnabled ?? (animation?.loop !== false);
    const loopEnabled = typeof nextLoopEnabled === "boolean" ? nextLoopEnabled : !currentLoop;
    const nextState = {
      ...currentState,
      loopEnabled
    };
    stepModuleAnimationStateRef.current = nextState;
    setStepModuleAnimationState(nextState);
  }, [selectedStepModuleDefinition]);

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
      const loopEnabled = currentState.loopEnabled ?? (animation.loop !== false);
      if (loopEnabled) {
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
    loop: selectedImplicitActiveAnimation?.loop !== false,
    loopEnabled: implicitAnimationState.loopEnabled ?? (selectedImplicitActiveAnimation?.loop !== false)
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
  // THE content signal: "is there anything on screen?", answered once for every format
  // from the capability table. Consumers (toolbar gates, CTA, preview mode, zoom pill,
  // alert blocking) read this instead of guessing which loaded object backs the viewport
  // — guessing `!selectedMeshData` is what left an implicit's buttons dead.
  const selectedViewportContent =
    viewportContentKind(selectedEntrySourceFormat) === VIEWPORT_CONTENT.IMPLICIT
      ? selectedImplicitRuntimeModel
      : selectedMeshData;
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

  const applyImplicitParameterValues = useCallback((values) => {
    markImplicitParameterInteraction();
    setImplicitParameterValues((current) => ({
      ...current,
      ...values
    }));
  }, [markImplicitParameterInteraction]);

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

  // THE parameter runtime: which store backs the selected entry's parameters, resolved
  // once from the capability table. Copy/paste/reset are written against this and work
  // for any format that declares a `params` source — a third store means one more arm
  // here, not a third copy of three clipboard handlers.
  //
  // The stores stay separate on purpose: they drive different recompute pipelines (a
  // STEP sidecar re-runs a build, an implicit re-uploads uniforms). Only the consumer
  // surface is shared.
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
      case PARAMETER_SOURCE.MODULE:
        return {
          label: "implicit",
          definition: selectedImplicitDefinition,
          values: implicitParameterValues,
          applyValues: applyImplicitParameterValues,
          reset: handleResetImplicitParameters
        };
      default:
        return null;
    }
  }, [
    applyImplicitParameterValues,
    applyStepModuleParameterValues,
    handleResetImplicitParameters,
    handleResetStepModuleParameters,
    implicitParameterValues,
    selectedEntrySourceFormat,
    selectedImplicitDefinition,
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

  const handleImplicitAnimationSelect = useCallback((animationId) => {
    const animation = findParameterAnimation(selectedImplicitDefinition, animationId);
    setImplicitAnimationState((current) => {
      const nextState = {
        ...current,
        activeId: animation?.id || "",
        playing: false,
        elapsedSec: 0,
        loopEnabled: animation?.loop !== false
      };
      return publishAnimationState(implicitAnimationStateRef, current, nextState);
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
      return publishAnimationState(implicitAnimationStateRef, current, nextState);
    });
  }, [selectedImplicitDefinition]);

  const handleImplicitAnimationReset = useCallback(() => {
    setImplicitAnimationState((current) => {
      const nextState = {
        ...current,
        elapsedSec: 0,
        playing: false
      };
      return publishAnimationState(implicitAnimationStateRef, current, nextState);
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
      return publishAnimationState(implicitAnimationStateRef, current, nextState);
    });
  }, [markImplicitParameterInteraction, selectedImplicitActiveAnimation]);

  const handleImplicitAnimationSpeedChange = useCallback((speed) => {
    setImplicitAnimationState((current) => {
      const nextState = {
        ...current,
        speed: clampNumber(speed, 0.1, 5)
      };
      return publishAnimationState(implicitAnimationStateRef, current, nextState);
    });
  }, []);

  const handleImplicitAnimationLoopToggle = useCallback((nextLoopEnabled) => {
    const animation = findParameterAnimation(
      selectedImplicitDefinition,
      implicitAnimationStateRef.current.activeId
    );
    setImplicitAnimationState((current) => {
      const currentLoop = current.loopEnabled ?? (animation?.loop !== false);
      const loopEnabled = typeof nextLoopEnabled === "boolean" ? nextLoopEnabled : !currentLoop;
      const nextState = {
        ...current,
        loopEnabled
      };
      return publishAnimationState(implicitAnimationStateRef, current, nextState);
    });
  }, [selectedImplicitDefinition]);

  // The animation half of the same idea as `activeParameterRuntime`: the toolbar's
  // Play button is a viewport control, so it asks the active runtime "do you have
  // clips, are you playing, can I toggle you" instead of reading the STEP store by
  // name. U0 flipped the button's gate to the `animations` capability but left it fed
  // from STEP state, so an implicit's clips still could not be played from the toolbar.
  const activeAnimationRuntime = useMemo(() => {
    switch (parameterSourceKind(selectedEntrySourceFormat)) {
      case PARAMETER_SOURCE.SIDECAR:
        return {
          available: selectedStepModuleHasAnimations,
          playing: selectedStepModuleAnimationViewState.playing,
          // A disabled sidecar is still loaded and still lists its clips; playing one
          // would drive a build nobody asked for.
          disabled: !stepModuleEnabled,
          onPlayToggle: handleStepModuleAnimationPlayToggle
        };
      case PARAMETER_SOURCE.MODULE:
        return {
          available: hasParameterAnimations(selectedImplicitDefinition),
          playing: selectedImplicitAnimationViewState.playing,
          disabled: false,
          onPlayToggle: handleImplicitAnimationPlayToggle
        };
      default:
        return null;
    }
  }, [
    handleImplicitAnimationPlayToggle,
    handleStepModuleAnimationPlayToggle,
    selectedEntrySourceFormat,
    selectedImplicitAnimationViewState.playing,
    selectedImplicitDefinition,
    selectedStepModuleAnimationViewState.playing,
    selectedStepModuleHasAnimations,
    stepModuleEnabled
  ]);

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
        const loopEnabled = current.loopEnabled ?? (selectedImplicitActiveAnimation.loop !== false);
        if (loopEnabled) {
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
  const implicitViewerLoading =
    !!selectedEntry &&
    implicitStatus !== ASSET_STATUS.ERROR &&
    (!selectedImplicitMatches || implicitStatus === ASSET_STATUS.LOADING);
  // A robot is loading until EVERY link mesh has landed. It is published once, complete,
  // so this stays true for the whole fetch and the card keeps reporting "loading meshes
  // 7/13" — a partially-drawn robot with no card gives no sign whether more is coming.
  const urdfViewerLoading =
    !!selectedEntry &&
    urdfStatus !== ASSET_STATUS.ERROR &&
    (!selectedUrdfMatches || urdfStatus === ASSET_STATUS.LOADING);
  // A fatal render-artifact error (not building) stops the loading spinner so the error
  // surfaces. Every artifact-managed format, not just STEP: a DXF or implicit build that
  // failed would otherwise spin forever behind its own error.
  const artifactBlocksRender =
    isArtifactManagedFormat(effectiveRenderFormat) &&
    selectedArtifact.status === "error";
  const meshViewerLoading =
    !!selectedEntry &&
    (selectedStepArtifactRenderPending || !artifactBlocksRender) &&
    status !== ASSET_STATUS.ERROR &&
    (!selectedMeshMatches || status === ASSET_STATUS.LOADING || selectedStepModuleLoading);
  // Implicits have their own arm again: they raymarch their GLSL, so "loading" means the
  // .implicit.js module is still being fetched, not that a mesh is. DXF has no arm -- it
  // renders its baked preview through the mesh path like everything else.
  const viewerLoading = {
    [ASSET_KIND.IMPLICIT]: implicitViewerLoading,
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
  const viewerLoadingFiles = useMemo(
    () => (effectiveViewerLoading && catalogSelectedEntry ? [fileKey(catalogSelectedEntry)] : []),
    [effectiveViewerLoading, catalogSelectedEntry]
  );
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
        [ASSET_KIND.IMPLICIT]: "Loading implicit CAD...",
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
  const selectedDrawingBendAxisCount = Array.isArray(selectedEntry?.bendAxisX)
    ? selectedEntry.bendAxisX.length
    : 0;
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
      status === ASSET_STATUS.ERROR ? error : "",
      selectedArtifact
    );
    return meshAlert || viewerRuntimeAlert;
  }, [
    effectiveRenderFormat,
    error,
    implicitError,
    implicitStatus,
    selectedEntry,
    selectedArtifact,
    selectedArtifactGenerating,
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
    () => createDirectorySessionThemeSlice(themeState),
    [themeState]
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
  // The file sheet and the theme sidebar are the same right-hand panel with
  // different contents: one open flag, one width, one resize handle, one inset
  // on the 3D viewport. Anything that sizes or offsets the panel uses this.
  const desktopRightPanelOpen = isDesktop && !previewMode && (
    themeEditing ||
    (tabToolsOpen && !!selectedFileSheetKind && selectedFileSheetHasSections)
  );
  const effectiveSidebarOpen = sidebarOpen && !previewMode;
  const desktopSidebarOpen = isDesktop && effectiveSidebarOpen && !previewMode;

  // Selecting a preset (or System) is the only "reset": it swaps the active
  // theme wholesale. The custom slot is kept so the user can flip back to it.
  const selectTheme = useCallback((nextThemeId) => {
    writeThemeState(nextThemeId, { onWriteError: handlePersistenceWriteError });
    setThemeState(readThemeSettingsState());
  }, [handlePersistenceWriteError]);

  // Any settings edit lands in the single custom slot and makes it active,
  // unless it happens to reproduce a preset exactly.
  const updateThemeSettings = useCallback((updater) => {
    setThemeState((current) => {
      const next = typeof updater === "function" ? updater(current.settings) : updater;
      const settings = normalizeThemeSettings(next);
      writeThemeSettings(settings, { onWriteError: handlePersistenceWriteError });
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

  const drawingGeometryUrl = selectedEntryIsDrawing
    ? String(selectedEntry?.relations?.drawingGeometry?.url || "")
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
    fetch(drawingGeometryUrl)
      .then((response) => (response.ok ? response.json() : null))
      .then((payload) => {
        if (cancelled) {
          return;
        }
        if (payload) {
          cache.set(drawingGeometryUrl, payload);
        }
        setDrawingGeometry(payload);
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

  const handleToggleThemeEditor = useCallback(() => {
    setThemeEditing((current) => {
      if (current) {
        return false;
      }
      setViewerAlertOpen(false);
      setTabToolsOpen(false);
      return true;
    });
  }, [setTabToolsOpen]);

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
    // the theme sidebar is the same panel and resizes the same width.
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
        viewerServerInfo
      })
  ), [
    activeStepArtifactGenerationFiles,
    selectedEntry,
    selectedFileSheetKind,
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
    hasDxfBendsPanel: selectedFileSheetKind === "dxf" && drawingBends.length > 0,
    hasDxfLayersPanel: selectedFileSheetKind === "dxf" && drawingLayers.length > 1,
    isSdf: selectedFileSheetKind === "sdf",
    motionEnabled: selectedFileSheetKind === "srdf" && moveit2ServerLive && selectedUrdfMotionEndEffectors.length > 0,
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
    moveit2ServerLive,
    selectedUrdfMotionEndEffectors,
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
        stepModule: {
          enabled: stepModuleEnabled,
          parameterValues: snapshotStepModuleParameterValues,
          animationState: snapshotStepModuleAnimationState
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
  }, [entryMap, readEntrySessionState]);

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
    selectedMateIdsRef.current = [];
    setSelectedMateIds([]);
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
    setReferenceQuery("");
    setSelectedReferenceIds([]);
    setSelectedMateIds([]);
    setSelectedPartIds([]);
    setSelectedRenderPartIdByAssemblyPartId({});
    setExpandedStepTreeNodeIds([]);
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
    getCachedImplicitState,
    getCachedMeshState,
    getCachedReferenceState,
    getCachedUrdfState,
    readEntrySessionState,
    selectedKey,
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
    applyColorSchemeToDocument(resolvedColorSchemeMode, document.documentElement);
  }, [resolvedColorSchemeMode]);

  useEffect(() => {
    document.documentElement.dataset.glassTone = cadWorkspaceGlassTone;
    return () => {
      delete document.documentElement.dataset.glassTone;
    };
  }, [cadWorkspaceGlassTone]);

  // Glass chrome (navbar, toolbars, popovers) tints toward the active scene
  // backdrop so the UI blends with whichever theme is selected.
  useEffect(() => {
    document.documentElement.style.setProperty(
      "--cad-scene-backdrop",
      resolveThemeSettingsBackdropColor(resolvedThemeSettings)
    );
    return () => {
      document.documentElement.style.removeProperty("--cad-scene-backdrop");
    };
  }, [resolvedThemeSettings]);

  useEffect(() => {
    const handleStorage = (event) => {
      const action = cadDirectoryStorageEventAction(event.key);
      if (action === CAD_DIRECTORY_STORAGE_EVENT_ACTION.IGNORE) {
        return;
      }
      try {
        setThemeState(readThemeSettingsState());
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
    if (assetKindForRenderFormat(selectedEntryRenderAssetFormat) !== ASSET_KIND.MESH) {
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
      return {
        loading: true,
        label: frame ? `${ARTIFACT_GENERATING_LABEL} ${frame.percent}%` : ARTIFACT_GENERATING_LABEL,
        title: frame
          ? `${frame.label}${frame.counts ? ` — ${frame.counts}` : ""}`
          : "Generator script is running"
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
    implicitLoadStage,
    implicitViewerLoading,
    meshLoadStage,
    meshLoadTargetFile,
    referenceLoadStage,
    referenceSelectionPending,
    referenceSelectionStatus,
    selectedEntry,
    selectedEntryHasDxf,
    selectedEntryHasImplicit,
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
    syncUrdfMotionTargetToJointValues(selectedUrdfFileRef, nextJointValues);
    clearUrdfMotionStatusForFile(selectedUrdfFileRef);
  }, [
    animateUrdfJointValues,
    clearUrdfMotionStatusForFile,
    clearTrackedUrdfGroupStateForFile,
    followUrdfJointValues,
    selectedUrdfFileRef,
    selectedUrdfJointValues,
    syncUrdfMotionTargetToJointValues
  ]);
  const handleResetUrdfPose = useCallback(() => {
    if (!selectedUrdfFileRef) {
      return;
    }
    cancelUrdfTrajectoryPlayback();
    clearTrackedUrdfGroupStateForFile(selectedUrdfFileRef);
    animateUrdfJointValues(selectedUrdfFileRef, selectedUrdfJointValues, defaultSelectedUrdfJointValues);
    syncUrdfMotionTargetToJointValues(selectedUrdfFileRef, defaultSelectedUrdfJointValues);
    clearUrdfMotionStatusForFile(selectedUrdfFileRef);
  }, [
    animateUrdfJointValues,
    cancelUrdfTrajectoryPlayback,
    clearUrdfMotionStatusForFile,
    clearTrackedUrdfGroupStateForFile,
    defaultSelectedUrdfJointValues,
    selectedUrdfFileRef,
    selectedUrdfJointValues,
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
    const groupStateId = String(groupState?.id || "").trim();
    if (groupStateId) {
      setSelectedUrdfGroupStateIdByFileRef((current) => ({
        ...current,
        [selectedUrdfFileRef]: groupStateId
      }));
    }
    animateUrdfJointValues(selectedUrdfFileRef, selectedUrdfJointValues, nextJointValues);
    syncUrdfMotionTargetToJointValues(selectedUrdfFileRef, nextJointValues);
    clearUrdfMotionStatusForFile(selectedUrdfFileRef);
  }, [
    animateUrdfJointValues,
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
      clearTrackedUrdfGroupStateForFile(selectedUrdfFileRef);
      if (trajectory) {
        playUrdfTrajectory(selectedUrdfFileRef, selectedUrdfJointValues, trajectory, nextJointValues);
      } else {
        animateUrdfJointValues(selectedUrdfFileRef, selectedUrdfJointValues, nextJointValues);
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
    animateUrdfJointValues,
    cancelUrdfTrajectoryPlayback,
    catalogRootDir,
    clearTrackedUrdfGroupStateForFile,
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
    setHoveredListPartId("");
    setHoveredModelPartId("");
    setHoveredListReferenceId("");
    setHoveredModelReferenceId("");
    setHoveredMateId("");
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
      selectedMateIdsRef.current.length ||
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
  // which shipped with the implicit render type and was unreachable while this handler
  // bailed on anything but STEP.
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
    const normalizedMode = mode === TAB_TOOL_MODE.DRAW || mode === TAB_TOOL_MODE.PAN
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

  const handleToggleFileSheet = useCallback(() => {
    if (!selectedFileSheetKind) {
      return;
    }
    setViewerAlertOpen(false);
    // Opening the file sheet while the theme sidebar is up replaces it.
    if (themeEditing) {
      setThemeEditing(false);
      setTabToolsOpen(true);
      if (!isDesktop) {
        setSidebarOpen(false);
      }
      return;
    }
    setTabToolsOpen((current) => {
      const nextOpen = !current;
      if (nextOpen && !isDesktop) {
        setSidebarOpen(false);
      }
      return nextOpen;
    });
  }, [themeEditing, isDesktop, selectedFileSheetKind, setTabToolsOpen]);

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
        if (kind === "filename") {
          copyText = targets.filename;
          statusLabel = "Copied filename";
        } else if (kind === "relativePath") {
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
      // Naming the file after "Copied filename" would just repeat what was copied.
      setCopyStatus(filename && copyText !== filename ? `${statusLabel} for ${filename}` : statusLabel);
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

  // One export handler for every exportable entry — STEP/assembly, DXF drawing, implicit
  // model. The server picks the producer from the source file, so the only thing that varies
  // here is the format the menu offered.
  const handleExportModelFile = useCallback(async (entry, format) => {
    const fileRef = entry ? fileKey(entry) : "";
    const exportFormat = String(format || "").trim().toLowerCase();
    if (!fileRef || !exportFormat || typeof window === "undefined") {
      return;
    }
    const busyKey = `${fileRef}:export:${exportFormat}`;
    setCopyStatus("");
    setScreenshotStatus("");
    setFileAccessBusyKey(busyKey);
    try {
      setCopyStatus(`Exporting ${exportFormatLabel(exportFormat)}...`);
      const payload = await requestModelExport({ file: fileRef, format: exportFormat });
      if (payload?.cancelled) {
        // User dismissed the native save dialog — clear the in-progress status, no error.
        setCopyStatus("");
        return;
      }
      const filename = String(payload?.filename || "").trim();
      const downloadUrl = String(payload?.downloadUrl || "").trim();
      if (downloadUrl) {
        const result = triggerUrlDownload(downloadUrl, { filename });
        setCopyStatus(result.message);
      } else {
        const savedPath = String(payload?.path || "").trim();
        const label = filename || exportFormatLabel(exportFormat);
        setCopyStatus(savedPath ? `Exported ${label} to ${savedPath}` : `Exported ${label}`);
      }
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "Export failed");
    } finally {
      setFileAccessBusyKey((current) => (current === busyKey ? "" : current));
    }
  }, []);

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
    setThemeEditing,
    setTabToolsOpen,
    setSidebarOpen,
    setTabToolMode
  });

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
    const viewportContent = selectedViewportContent;
    if (viewerLoading || !viewportContent || previewMode) {
      return;
    }
    previewUiStateRef.current = {
      sidebarOpen,
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
  const fileSheetOpen = !!selectedFileSheetKind && selectedFileSheetHasSections && tabToolsOpen && !previewMode && !themeEditing;
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
          drawingThicknessMm={selectedEntryIsDrawing ? drawingThicknessMm : 0}
          onCameraZoomPercentChange={setViewerZoomPercent}
          renderPartsIndividually={isUrdfView || Boolean(selectedStepParameterRuntime)}
          stepParameters={selectedStepParameterRuntime}
          selectedMeshData={selectedMeshData}
          selectedKey={selectedKey}
          selectedImplicitModel={selectedImplicitRuntimeModel}
          implicitDynamicRenderActive={implicitDynamicRenderActive}
          implicitGraphicsSettings={implicitGraphicsSettings}
          missingFileRef={missingFileRef}
          viewerServerInfo={viewerServerInfo}
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
          assemblyPickingActive={viewerInAssemblyMode}
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
          boundsAnimationActive={robotBoundsAnimationActive}
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
          copyReferenceTipActive={copyReferenceTipActive}
          panToolActive={panToolActive}
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
          entryHasUrdf={entryHasUrdf}
          activeStepArtifactGenerationFile={activeStepArtifactGenerationFiles}
              loadingFiles={viewerLoadingFiles}
          stepArtifactGenerationAvailable={stepArtifactGenerationAvailable}
          filenameLoadActivity={filenameLoadActivity}
          selectedStepSourceStatus={selectedStepSourceStatus}
          canRevealFileAssets={fileRevealAvailable}
          canCopyFileAssetLinks={fileLinkCopyAvailable}
          canCopyFileAssetPaths={filePathCopyAvailable}
          fileAccessBusyKey={fileAccessBusyKey}
          onDownloadFileAsset={handleDownloadFileAsset}
          onExportModelFile={handleExportModelFile}
          onRevealFileAsset={handleRevealFileAsset}
          onRevealInExplorerView={handleRevealEntryInExplorerView}
          onCopyFileAssetReference={handleCopyFileAssetReference}
          fileSheetKind={selectedFileSheetHasSections ? selectedFileSheetKind : ""}
          fileSheetOpen={fileSheetOpen}
          onToggleFileSheet={handleToggleFileSheet}
          themeEditing={themeEditing}
          onToggleThemeEditor={handleToggleThemeEditor}
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
              canRevealFileAssets={fileRevealAvailable}
              canCopyFileAssetLinks={fileLinkCopyAvailable}
              canCopyFileAssetPaths={filePathCopyAvailable}
              fileAccessBusyKey={fileAccessBusyKey}
              onDownloadFileAsset={handleDownloadFileAsset}
              onExportModelFile={handleExportModelFile}
              onRevealFileAsset={handleRevealFileAsset}
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
                urdfPosePickerAvailable={selectedUrdfMoveIt2ActionsEnabled}
                urdfPosePickerActive={urdfPosePickerActive}
                handleToggleUrdfPosePicker={handleToggleUrdfPosePicker}
                animationAvailable={!!activeAnimationRuntime?.available}
                animationPlaying={!!activeAnimationRuntime?.playing}
                animationDisabled={!!activeAnimationRuntime?.disabled}
                handleAnimationPlayToggle={activeAnimationRuntime?.onPlayToggle}
                drawToolActive={drawToolActive}
                panToolActive={panToolActive}
                handleSelectTabToolMode={handleSelectTabToolMode}
                viewerLoading={viewerLoading}
                selectedMeshData={selectedMeshData}
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
                handleExitPreviewMode={handleExitPreviewMode}
                handleScreenshotCopy={handleScreenshotCopy}
                onExportModelFile={handleExportModelFile}
                fileAccessBusyKey={fileAccessBusyKey}
              />

              {!previewMode && !selectedEntry && !missingFileRef && !fileParamSelectionPending ? (
                <CadWorkspaceHome
                  entries={catalogEntries}
                  onSelectEntry={handleSelectEntry}
                  catalogHydrated={catalogHydrated}
                  catalogRefreshing={catalogRefreshing}
                  catalogError={catalogError}
                />
              ) : null}

              <ViewerLoadingOverlay
                viewerLoading={effectiveViewerLoading}
                previewMode={previewMode}
                progress={selectedArtifactProgress}
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
                stepTreeRoot={displayStepTreeRoot}
                assemblyMates={selectedAssemblyMates}
                expandedTreeNodeIds={expandedStepTreeNodeIds}
                loadableTreeNodeIds={loadableStepTreeTopologyNodeIds}
                selectedPartIds={selectedPartIds}
                selectedReferenceIds={selectedReferenceIds}
                selectedReferences={selectedReferenceItems}
                selectedMateIds={selectedMateIds}
                selectableNodeIds={isolatedStepTreeSelectableNodeIds}
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
                  onResetParameters: handleResetParameters,
                  onAnimationSelect: handleStepModuleAnimationSelect,
                  onAnimationPlayToggle: handleStepModuleAnimationPlayToggle,
                  onAnimationReset: handleStepModuleAnimationReset,
                  onAnimationScrub: handleStepModuleAnimationScrub,
                  onAnimationSpeedChange: handleStepModuleAnimationSpeedChange,
                  onAnimationLoopToggle: handleStepModuleAnimationLoopToggle,
                  onEnabledChange: handleStepModuleEnabledChange,
                  onCopyParams: handleCopyParameters,
                  onPasteParams: handlePasteParameters
                }}
                fileDownloadAvailable={fileLinkCopyAvailable}
                viewerServerInfo={viewerServerInfo}
                localFileOpenAvailable={fileRevealAvailable}
                fileAccessBusyKey={fileAccessBusyKey}
                onOpenFileAsset={handleRevealFileAsset}
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
                onStartResize={handleStartFileSheetResize}
                fileDownloadAvailable={fileLinkCopyAvailable}
                viewerServerInfo={viewerServerInfo}
                localFileOpenAvailable={fileRevealAvailable}
                fileAccessBusyKey={fileAccessBusyKey}
                onOpenFileAsset={handleRevealFileAsset}
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
                onStartResize={handleStartFileSheetResize}
                fileDownloadAvailable={fileLinkCopyAvailable}
                viewerServerInfo={viewerServerInfo}
                localFileOpenAvailable={fileRevealAvailable}
                fileAccessBusyKey={fileAccessBusyKey}
                onOpenFileAsset={handleRevealFileAsset}
                suppressDynamicMetadataStatus={selectedArtifactGenerating}
                statusItems={selectedFileStatusItems}
                themeTabs={themeTabs}
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
                  onResetParameters: handleResetParameters,
                  onAnimationSelect: handleImplicitAnimationSelect,
                  onAnimationPlayToggle: handleImplicitAnimationPlayToggle,
                  onAnimationReset: handleImplicitAnimationReset,
                  onAnimationScrub: handleImplicitAnimationScrub,
                  onAnimationSpeedChange: handleImplicitAnimationSpeedChange,
                  onAnimationLoopToggle: handleImplicitAnimationLoopToggle,
                  onCopyParams: handleCopyParameters,
                  onPasteParams: handlePasteParameters
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
                suppressDynamicMetadataStatus={selectedArtifactGenerating}
                statusItems={selectedFileStatusItems}
                themeTabs={themeTabs}
                openSectionIds={effectiveFileSheetOpenSectionIds}
                onOpenSectionIdsChange={handleFileSheetOpenSectionIdsChange}
              />
            ) : null}

            {themeEditing ? (
              <ThemeEditorPanel
                open
                isDesktop={isDesktop}
                width={activeSheetWidth || tabToolsWidth}
                onClose={closeThemeEditor}
                onStartResize={handleStartFileSheetResize}
                themeSettings={themeSettings}
                themeId={themeId}
                resolvedColorSchemeMode={resolvedColorSchemeMode}
                onSelectTheme={selectTheme}
                updateThemeSettings={updateThemeSettings}
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

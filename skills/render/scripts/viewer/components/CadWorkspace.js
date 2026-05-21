"use client";

import { startTransition, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeftRight, ArrowRight, Circle, Eraser, Minus, PaintBucket, PenTool, Square } from "lucide-react";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import CadRenderPane from "./workbench/CadRenderPane";
import DxfFileSheet from "./workbench/DxfFileSheet";
import FileExplorerSidebar from "./workbench/FileExplorerSidebar";
import { ThemeSettingsSections } from "./workbench/ThemeSettingsPopover";
import MeshFileSheet from "./workbench/MeshFileSheet";
import StepFileSheet from "./workbench/StepFileSheet";
import StatusToast from "./workbench/StatusToast";
import UrdfFileSheet from "./workbench/UrdfFileSheet";
import ExplorerAlertDialog from "./workbench/ExplorerAlertDialog";
import ExplorerLoadingOverlay from "./workbench/ExplorerLoadingOverlay";
import FloatingToolBar from "./workbench/FloatingToolBar";
import CadWorkspaceTopBar from "./workbench/CadWorkspaceTopBar";
import { useCadAssets } from "./workbench/hooks/useCadAssets";
import {
  resolveDesktopPanelWidths,
  useCadWorkspaceLayout
} from "./workbench/hooks/useCadWorkspaceLayout";
import { useCadWorkspaceSelection } from "./workbench/hooks/useCadWorkspaceSelection";
import { useCadWorkspaceSession } from "./workbench/hooks/useCadWorkspaceSession";
import { useCadWorkspaceSelectors } from "./workbench/hooks/useCadWorkspaceSelectors";
import { useCadWorkspaceShortcuts } from "./workbench/hooks/useCadWorkspaceShortcuts";
import {
  applyColorSchemeToDocument,
  DEFAULT_COLOR_SCHEME_ID
} from "../lib/colorScheme";
import {
  getThemePresetIdForSettings,
  inferThemeSettingsSceneTone,
  normalizeThemeSettings,
  resolveSystemThemePresetId
} from "../lib/themeSettings";
import { clonePerspectiveSnapshot } from "../lib/perspective";
import {
  ASSET_STATUS,
  DRAWING_TOOL,
  RENDER_FORMAT,
  REFERENCE_STATUS,
  TAB_TOOL_MODE
} from "../lib/workbench/constants";
import {
  buildAvailableThemePresets,
  cloneDrawingStrokes,
  cloneTabSnapshot,
  createTabRecord,
  deleteCustomThemePreset,
  drawingStrokesEqual,
  getAvailableThemePresetIdForSettings,
  readCustomThemePresets,
  readThemeSettingsState,
  saveCustomThemePreset,
  THEME_STORAGE_KEY,
  writeCustomThemePresetLibrary,
  tabSnapshotEqual,
  CAD_WORKSPACE_DEFAULT_SIDEBAR_WIDTH,
  CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH
} from "../lib/workbench/persistence";
import {
  createFileSessionSnapshot,
  normalizeFileSessionNamespace,
  pruneFileSessionState,
  readFileSessionState,
  writeFileSessionState
} from "../lib/workbench/fileSessionState";
import {
  buildCadViewState,
  formatCadViewStateForClipboard
} from "../lib/workbench/viewState";
import {
  CAD_WORKSPACE_LAYOUT_MODE,
  getCadWorkspaceLayoutMode,
  shouldCadWorkspaceDefaultFileExplorerOpen,
  shouldCadWorkspaceDefaultFileSettingsOpen
} from "../lib/workbench/breakpoints";
import {
  buildSidebarDirectoryTree,
  cadPathForEntry,
  collectAncestorDirectoryIds,
  collectSidebarDirectoryIds,
  findEntryByUrlPath,
  fileKey,
  readCadParam,
  readCadRefQueryParams,
  selectedEntryKeyFromUrl,
  sidebarDirectoryIdForEntry,
  sidebarLabelForEntry,
  writeCadParam,
  writeCadRefQueryParams,
} from "../lib/workbench/sidebar";
import { buildCadRefToken, parseCadRefSelector, parseCadRefToken, sortCadRefSelectors } from "../lib/cadRefs";
import { loadRenderSelectorBundle } from "../lib/renderAssetClient";
import {
  buildDxfPreviewMeshData,
  extractOrderedDxfBendLines,
  normalizeDxfBendAngleDeg,
  normalizeDxfBendDirection,
  normalizeDxfBendSettings,
  DEFAULT_DXF_PREVIEW_THICKNESS_MM,
  normalizeDxfPreviewThicknessMm
} from "../lib/dxf/buildPreviewMesh";
import {
  applyUrdfPoseToMeshData,
  buildDefaultUrdfJointValues,
  buildUrdfMeshGeometry,
  clampJointValueDeg,
  linkOriginInFrame,
  rootPointInFrame
} from "../lib/urdf/kinematics";
import {
  jointValuesByNameToNative,
  measureUrdfMotionResult,
  nativeJointValueToDisplay,
  normalizeMotionTargetPosition,
  validateUrdfMotionTrajectory,
  validateUrdfMotionJointValues
} from "../lib/urdf/motion";
import { checkMoveIt2ServerLive, moveit2ServerEnabled, requestMoveIt2Server } from "../lib/urdf/moveit2ServerClient";
import { jointValueMapsClose } from "../lib/urdf/jointAnimation";
import {
  DEFAULT_STEP_CLIP_SETTINGS,
  normalizeStepClipSettings
} from "../lib/explorer/clipPlane";
import { buildSelectorRuntime } from "../lib/selectors/runtime";
import {
  buildAssemblyLeafToNodePickMap,
  descendantLeafPartIds,
  findAssemblyNode,
  flattenAssemblyNodes,
  flattenAssemblyLeafParts,
  leafPartIdsForAssemblySelection,
  resolveAssemblyPickedPartId
} from "../lib/assembly/meshData";
import {
  buildStepTreeRoot,
  collectStepTreeAncestorIds,
  STEP_MODEL_ROOT_ID,
  STEP_MODEL_RENDER_PART_ID,
  stepTreeNodeChildren
} from "../lib/step/stepTree";
import {
  loadStepModuleDefinition,
  normalizeParameterValue,
  normalizeStepModuleParameterValues
} from "../common/stepModule";
import { copyTextToClipboard } from "../lib/clipboard";

const DEFAULT_DOCUMENT_TITLE = "CAD Explorer";
const EMPTY_LIST = Object.freeze([]);
const CAD_BUILD_COMMANDS = {
  dxf: "python skills/cad/scripts/dxf",
  step: "python skills/cad/scripts/step",
  urdf: "python skills/urdf/scripts/urdf",
  sdf: "python skills/sdf/scripts/sdf"
};
const MOVEIT2_SERVER_ENABLED = moveit2ServerEnabled();
const URDF_POSE_PICKER_DEFAULT_CENTER = Object.freeze([0, 0, 0]);
const DESKTOP_SIDEBAR_MIN_WIDTH = 150;
const DESKTOP_SIDEBAR_MAX_WIDTH = 520;
const DEFAULT_SIDEBAR_WIDTH = CAD_WORKSPACE_DEFAULT_SIDEBAR_WIDTH;
const DESKTOP_TAB_TOOLS_MIN_WIDTH = 240;
const DESKTOP_TAB_TOOLS_MAX_WIDTH = 560;
const DEFAULT_TAB_TOOLS_WIDTH = CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH;
const CAD_WORKSPACE_TOP_BAR_HEIGHT = 44;
const STEP_MODULE_TRANSFORM_SELECTION_DISABLED_REASON =
  "Tree selection is disabled while Parameters move parts. Turn off Parameters to enable selection.";

function toFiniteNumber(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function clampNumber(value, min, max) {
  return Math.min(Math.max(toFiniteNumber(value, min), min), max);
}

function shallowObjectValuesEqual(left, right) {
  const leftKeys = Object.keys(left || {});
  const rightKeys = Object.keys(right || {});
  if (leftKeys.length !== rightKeys.length) {
    return false;
  }
  return leftKeys.every((key) => Object.hasOwn(right || {}, key) && left?.[key] === right?.[key]);
}

function findStepModuleAnimation(definition, animationId) {
  const animations = Array.isArray(definition?.animations) ? definition.animations : [];
  if (!animations.length) {
    return null;
  }
  const normalizedId = String(animationId || "").trim();
  return animations.find((animation) => animation.id === normalizedId) || animations[0] || null;
}

function buildDefaultStepModuleAnimationState(definition) {
  const animation = findStepModuleAnimation(definition, "");
  return {
    activeId: animation?.id || "",
    playing: false,
    elapsedSec: 0,
    speed: 1
  };
}

function isRobotRenderFormat(format) {
  return format === RENDER_FORMAT.URDF || format === RENDER_FORMAT.SDF;
}

function animationNowMs() {
  if (typeof performance !== "undefined" && typeof performance.now === "function") {
    return performance.now();
  }
  return Date.now();
}

function readWorkspaceViewportWidth() {
  if (typeof window === "undefined") {
    return 1600;
  }
  const width = Number(window.innerWidth);
  return Number.isFinite(width) && width > 0 ? width : 1600;
}

function readWorkspaceLayoutMode() {
  return getCadWorkspaceLayoutMode(readWorkspaceViewportWidth());
}

function cloneJointValueMap(values) {
  if (!values || typeof values !== "object") {
    return {};
  }
  return Object.fromEntries(
    Object.entries(values)
      .map(([name, value]) => [String(name || "").trim(), toFiniteNumber(value, 0)])
      .filter(([name]) => name)
  );
}

function srdfGroupStateJointValuesToDisplay(urdfData, jointValuesByName) {
  if (!jointValuesByName || typeof jointValuesByName !== "object") {
    return {};
  }
  const joints = Array.isArray(urdfData?.joints) ? urdfData.joints : [];
  const jointByName = new Map(joints.map((joint) => [String(joint?.name || ""), joint]).filter(([name]) => name));
  return Object.fromEntries(
    Object.entries(jointValuesByName)
      .map(([name, value]) => {
        const jointName = String(name || "").trim();
        const joint = jointByName.get(jointName);
        return jointName && joint ? [jointName, nativeJointValueToDisplay(joint, value)] : null;
      })
      .filter(Boolean)
  );
}

function jointValueSubsetClose(values, subset) {
  const targetValues = cloneJointValueMap(subset);
  const targetNames = Object.keys(targetValues);
  if (!targetNames.length) {
    return false;
  }
  const currentValues = Object.fromEntries(targetNames.map((name) => [name, values?.[name]]));
  return jointValueMapsClose(currentValues, targetValues);
}

function interpolateTrajectoryJointValues(trajectory, elapsedSec, fallbackValues = {}) {
  const points = Array.isArray(trajectory?.points) ? trajectory.points : [];
  if (!points.length) {
    return cloneJointValueMap(fallbackValues);
  }
  const firstPoint = points[0];
  if (elapsedSec <= toFiniteNumber(firstPoint.timeFromStartSec, 0)) {
    return {
      ...cloneJointValueMap(fallbackValues),
      ...cloneJointValueMap(firstPoint.positionsByNameDeg)
    };
  }
  for (let index = 1; index < points.length; index += 1) {
    const previousPoint = points[index - 1];
    const nextPoint = points[index];
    const previousTime = toFiniteNumber(previousPoint.timeFromStartSec, 0);
    const nextTime = toFiniteNumber(nextPoint.timeFromStartSec, previousTime);
    if (elapsedSec > nextTime) {
      continue;
    }
    const span = Math.max(nextTime - previousTime, 1e-6);
    const progress = Math.min(Math.max((elapsedSec - previousTime) / span, 0), 1);
    const previousValues = cloneJointValueMap(previousPoint.positionsByNameDeg);
    const nextValues = cloneJointValueMap(nextPoint.positionsByNameDeg);
    const interpolated = {};
    for (const [jointName, nextValue] of Object.entries(nextValues)) {
      const previousValue = Object.hasOwn(previousValues, jointName) ? previousValues[jointName] : nextValue;
      interpolated[jointName] = previousValue + ((nextValue - previousValue) * progress);
    }
    return {
      ...cloneJointValueMap(fallbackValues),
      ...interpolated
    };
  }
  return {
    ...cloneJointValueMap(fallbackValues),
    ...cloneJointValueMap(points[points.length - 1].positionsByNameDeg)
  };
}

function roundedUrdfJointValue(value) {
  const numericValue = toFiniteNumber(value, 0);
  const rounded = Math.round(numericValue * 1000) / 1000;
  return Object.is(rounded, -0) ? 0 : rounded;
}

function emptyUrdfPosePickerState() {
  return {
    fileRef: "",
    originalPerspective: null
  };
}

function normalizePoint3(value) {
  if (!Array.isArray(value) || value.length < 3) {
    return null;
  }
  const point = [Number(value[0]), Number(value[1]), Number(value[2])];
  return point.every(Number.isFinite) ? point : null;
}

function buildUrdfJointAnglesCopyText(joints, jointValues) {
  const movableJoints = Array.isArray(joints) ? joints : [];
  return JSON.stringify(
    Object.fromEntries(
      movableJoints.map((joint) => {
        const jointName = String(joint?.name || "").trim();
        const value = roundedUrdfJointValue(jointValues?.[jointName] ?? joint?.defaultValueDeg ?? 0);
        return [jointName, value];
      }).filter(([name]) => name)
    ),
    null,
    2
  );
}

function meshAssetKeyForEntry(entry) {
  return entry?.kind === RENDER_FORMAT.STL || entry?.kind === RENDER_FORMAT.THREE_MF || entry?.kind === RENDER_FORMAT.GLB
    ? entry.kind
    : "glb";
}

function buildMeshCacheKey(entry) {
  const fileRef = fileKey(entry);
  const meshHash = String(
    entry?.kind === "assembly"
      ? [entryAssetHash(entry, "topology"), entryAssetHash(entry, "glb")].filter(Boolean).join(":")
      : entryAssetHash(entry, meshAssetKeyForEntry(entry))
  );
  return fileRef && meshHash ? `${fileRef}:${meshHash}` : "";
}

function buildReferenceCacheKey(entry) {
  const fileRef = fileKey(entry);
  const referenceHash = [
    entryAssetHash(entry, "selectorTopology"),
  ].filter(Boolean).join(":") || String(entry?.step?.hash || "");
  return fileRef && referenceHash ? `${fileRef}:${referenceHash}` : "";
}

function buildDxfCacheKey(entry) {
  const fileRef = fileKey(entry);
  const dxfHash = entryAssetHash(entry, "dxf");
  return fileRef && dxfHash ? `${fileRef}:${dxfHash}` : "";
}

function buildUrdfCacheKey(entry) {
  const fileRef = fileKey(entry);
  const urdfHash = entryUrdfAssetHash(entry);
  return fileRef && urdfHash ? `${fileRef}:${urdfHash}` : "";
}

function entryAsset(entry, key) {
  return entry?.assets?.[key] || null;
}

function entryAssetUrl(entry, key) {
  return String(entryAsset(entry, key)?.url || "").trim();
}

function entryAssetHash(entry, key) {
  return String(entryAsset(entry, key)?.hash || "").trim();
}

function entrySelectorTopologyAssetUrl(entry) {
  return entryAssetUrl(entry, "selectorTopology") || entryAssetUrl(entry, "topology") || entryAssetUrl(entry, "glb");
}

function entryUrdfAssetHash(entry) {
  return [
    entryAssetHash(entry, "urdf"),
    entryAssetHash(entry, "srdf"),
    entryAssetHash(entry, "sdf")
  ].filter(Boolean).join(":");
}

function buildCadCommand(fileRef, entry = null) {
  const sourceFormat = entrySourceFormat(entry);
  if (sourceFormat === RENDER_FORMAT.DXF) {
    return `${CAD_BUILD_COMMANDS.dxf} ${fileRef}`;
  }
  if (sourceFormat === RENDER_FORMAT.URDF) {
    return String(entry?.kind || "").trim().toLowerCase() === "srdf" ? "" : `${CAD_BUILD_COMMANDS.urdf} ${fileRef}`;
  }
  if (sourceFormat === RENDER_FORMAT.SDF) {
    return `${CAD_BUILD_COMMANDS.sdf} ${fileRef}`;
  }
  if (sourceFormat === RENDER_FORMAT.STL) {
    return "";
  }
  if (sourceFormat === RENDER_FORMAT.THREE_MF) {
    return "";
  }
  if (sourceFormat === RENDER_FORMAT.GLB) {
    return "";
  }
  return `${CAD_BUILD_COMMANDS.step} ${fileRef}`;
}

function entryHasMesh(entry) {
  if (entrySourceFormat(entry) === RENDER_FORMAT.STEP) {
    return Boolean(
      entry?.stepArtifact?.ok &&
      entryAssetUrl(entry, "glb") &&
      entryAssetHash(entry, "glb")
    );
  }
  const meshKey = meshAssetKeyForEntry(entry);
  return Boolean(entryAssetUrl(entry, meshKey) && entryAssetHash(entry, meshKey));
}

function entryHasUrdf(entry) {
  const kind = String(entry?.kind || "").trim().toLowerCase();
  if (kind === RENDER_FORMAT.SDF) {
    return Boolean(entryAssetUrl(entry, "sdf") && entryAssetHash(entry, "sdf"));
  }
  return Boolean(entryAssetUrl(entry, "urdf") && entryAssetHash(entry, "urdf"));
}

function entryHasReferences(entry) {
  return Boolean(
    entrySourceFormat(entry) === RENDER_FORMAT.STEP &&
    entry?.stepArtifact?.ok &&
    entryAssetUrl(entry, "glb") &&
    entryAssetHash(entry, "selectorTopology")
  );
}

function entryHasDxf(entry) {
  return Boolean(entryAssetUrl(entry, "dxf") && entryAssetHash(entry, "dxf"));
}

function entrySourceFormat(entry) {
  const kind = String(entry?.kind || "").trim().toLowerCase();
  if (kind === "dxf") {
    return RENDER_FORMAT.DXF;
  }
  if (kind === RENDER_FORMAT.STL) {
    return RENDER_FORMAT.STL;
  }
  if (kind === RENDER_FORMAT.THREE_MF) {
    return RENDER_FORMAT.THREE_MF;
  }
  if (kind === RENDER_FORMAT.GLB) {
    return RENDER_FORMAT.GLB;
  }
  if (kind === RENDER_FORMAT.URDF || kind === "srdf") {
    return RENDER_FORMAT.URDF;
  }
  if (kind === RENDER_FORMAT.SDF) {
    return RENDER_FORMAT.SDF;
  }
  return RENDER_FORMAT.STEP;
}

function fileSheetKindForEntry(entry) {
  if (!entry) {
    return "";
  }
  const kind = String(entry?.kind || "").trim().toLowerCase();
  if (kind === "dxf") {
    return "dxf";
  }
  if (kind === "urdf") {
    return "urdf";
  }
  if (kind === "srdf") {
    return "srdf";
  }
  if (kind === "sdf") {
    return "sdf";
  }
  if (entrySourceFormat(entry) === RENDER_FORMAT.STEP) {
    return "step";
  }
  if ([RENDER_FORMAT.STL, RENDER_FORMAT.THREE_MF, RENDER_FORMAT.GLB].includes(entrySourceFormat(entry))) {
    return "mesh";
  }
  return "";
}

function normalizeReferenceList(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((reference) => reference && typeof reference === "object")
    .map((reference) => ({
      ...reference,
      id: String(reference.id || "").trim(),
      label: String(reference.label || reference.id || "Reference").trim() || "Reference",
      summary: String(reference.summary || reference.shortSummary || "").trim(),
      shortSummary: String(reference.shortSummary || reference.summary || "").trim(),
      copyText: String(reference.copyText || "").trim(),
      partId: String(reference.partId || "").trim(),
      entityType: String(reference.entityType || "").trim(),
      selectorType: String(reference.selectorType || "").trim(),
      normalizedSelector: String(reference.normalizedSelector || "").trim(),
      displaySelector: String(reference.displaySelector || "").trim()
    }))
    .filter((reference) => reference.id);
}

function readReferenceCounts(referencePayload = null) {
  return {
    faces: Math.max(0, Number(referencePayload?.manifest?.stats?.faceCount || 0)),
    edges: Math.max(0, Number(referencePayload?.manifest?.stats?.edgeCount || 0))
  };
}

function buildNormalizedReferenceState(entry, referencePayload = null, {
  copyCadPath,
  partId = "",
  transform = null,
  remapOccurrenceId = "",
  remapOccurrencePrefix = null
} = {}) {
  const counts = readReferenceCounts(referencePayload);

  const selectorRuntime = buildSelectorRuntime(referencePayload, {
    copyCadPath: copyCadPath || cadPathForEntry(entry),
    partId,
    transform,
    remapOccurrenceId,
    remapOccurrencePrefix
  });
  const references = normalizeReferenceList(selectorRuntime.references);
  return {
    fileRef: fileKey(entry),
    kind: entry.kind,
    referenceHash: buildReferenceCacheKey(entry),
    stepRelPath: entry?.step?.path || "",
    stepHash: String(selectorRuntime.stepHash || entry?.step?.hash || ""),
    counts: {
      faces: Number(selectorRuntime.faces?.length || 0),
      edges: Number(selectorRuntime.edges?.length || 0)
    },
    parts: [],
    selectorRuntime,
    references,
    disabledReason: ""
  };
}

function parseAssemblyPartReferenceSelectionId(referenceId) {
  const normalizedReferenceId = String(referenceId || "").trim();
  const prefix = "assembly-part:";
  if (normalizedReferenceId.startsWith(prefix)) {
    const partId = normalizedReferenceId.slice(prefix.length).trim();
    if (!partId) {
      return null;
    }
    return { partId };
  }
  if (normalizedReferenceId.startsWith("topology|")) {
    const parts = normalizedReferenceId.split("|");
    const partId = String(parts[1] || "").trim();
    if (!partId) {
      return null;
    }
    return { partId };
  }
  return null;
}

function buildCadRefGroupKey(cadPath, selector = "") {
  const compactCadPath = String(cadPath || "").trim();
  if (!compactCadPath) {
    return "";
  }
  const groupKind = String(selector || "").trim() || "root";
  return `${compactCadPath}::${groupKind}`;
}

function ensureCadRefGroup(groups, outputOrder, groupKey, cadPath) {
  if (!groupKey) {
    return null;
  }
  let group = groups.get(groupKey);
  if (group) {
    return group;
  }
  group = {
    cadPath,
    selectors: [],
    seenSelectors: new Set()
  };
  groups.set(groupKey, group);
  outputOrder.push({
    kind: "group",
    key: groupKey
  });
  return group;
}

function appendUniquePlainLine(plainLines, outputOrder, text, key = "") {
  const normalizedText = String(text || "").trim();
  const normalizedKey = String(key || "").trim() || normalizedText;
  if (!normalizedText || !normalizedKey || plainLines.has(normalizedKey)) {
    return false;
  }
  plainLines.set(normalizedKey, normalizedText);
  outputOrder.push({
    kind: "plain",
    key: normalizedKey
  });
  return true;
}

function appendCadRefText(groups, plainLines, outputOrder, text, key = "") {
  const normalizedText = String(text || "").trim();
  if (!normalizedText) {
    return 0;
  }
  const parsedToken = parseCadRefToken(normalizedText);
  if (!parsedToken) {
    appendUniquePlainLine(plainLines, outputOrder, normalizedText, key);
    return 0;
  }

  const { cadPath, selectors } = parsedToken;
  if (!selectors.length) {
    const group = ensureCadRefGroup(groups, outputOrder, buildCadRefGroupKey(cadPath, "root"), cadPath);
    if (!group || group.seenSelectors.has("")) {
      return 0;
    }
    group.seenSelectors.add("");
    return 1;
  }

  const group = ensureCadRefGroup(groups, outputOrder, buildCadRefGroupKey(cadPath, "selectors"), cadPath);
  if (!group) {
    return 0;
  }

  let addedCount = 0;
  for (const selector of selectors) {
    if (group.seenSelectors.has(selector)) {
      continue;
    }
    group.seenSelectors.add(selector);
    group.selectors.push(selector);
    addedCount += 1;
  }
  return addedCount;
}

function copySelectedReferenceText(references) {
  const groups = new Map();
  const plainLines = new Map();
  const outputOrder = [];

  for (const reference of references) {
    appendCadRefText(
      groups,
      plainLines,
      outputOrder,
      String(reference?.copyText || "").trim(),
      String(reference?.id || "").trim()
    );
  }

  const lines = outputOrder
    .map((item) => {
      if (item.kind === "plain") {
        return plainLines.get(item.key) || "";
      }
      const group = groups.get(item.key);
      if (!group) {
        return "";
      }
      return buildCadRefToken({
        cadPath: group.cadPath,
        selectors: item.key.endsWith("::selectors") ? sortCadRefSelectors(group.selectors) : []
      });
    })
    .filter(Boolean);

  return {
    text: lines.join("\n")
  };
}

function buildAssemblyPartCopyText(part, entry) {
  const cadPath = cadPathForEntry(entry);
  if (!cadPath) {
    return "";
  }

  const partId = String(part?.id || "").trim();
  const selector = String(part?.occurrenceId || partId).trim();
  if (!partId || !selector) {
    return "";
  }
  const partName = String(part?.name || partId).trim() || partId;
  return `${buildCadRefToken({
    cadPath,
    selector
  })} Assembly part "${partName}"`;
}

function buildWholeStepEntryCopyReference(entry) {
  const cadPath = cadPathForEntry(entry);
  if (!cadPath) {
    return null;
  }
  return {
    id: "step-entry:whole",
    copyText: `${buildCadRefToken({ cadPath })} STEP file`
  };
}

function buildSelectionCopyPayload({ references = [], parts = [], entry = null } = {}) {
  const referencesForCopy = Array.isArray(references) ? [...references] : [];
  const missingPartNames = [];

  for (const part of parts) {
    const copyText = buildAssemblyPartCopyText(part, entry);
    if (!copyText) {
      missingPartNames.push(String(part?.name || part?.id || "part"));
      continue;
    }
    referencesForCopy.push({
      id: `assembly-part:${String(part?.id || "").trim()}`,
      copyText
    });
  }

  const { text: referenceText } = copySelectedReferenceText(referencesForCopy);
  const lines = String(referenceText || "").split("\n").map((line) => line.trim()).filter(Boolean);

  return {
    lines,
    copiedCount: referencesForCopy.length,
    missingPartNames
  };
}

function buildSelectionCopyButtonLabel(lines, { count = 0, limit = 1 } = {}) {
  const copyLines = Array.isArray(lines) ? lines : [];
  const normalizedLimit = Math.max(1, Number(limit) || 1);
  const tokens = copyLines
    .map((line) => parseCadRefToken(String(line || "").trim())?.token || String(line || "").trim())
    .filter(Boolean);

  if (!tokens.length) {
    return "Copy refs";
  }

  const requestedCount = Math.trunc(Number(count) || 0);
  const copiedCount = requestedCount > 0 ? requestedCount : tokens.length;
  const visibleTokens = tokens.slice(0, normalizedLimit);
  return `Copy [${copiedCount} ref${copiedCount === 1 ? "" : "s"}] ${visibleTokens.join(", ")}`;
}

function orderedStringListEqual(a, b) {
  if (a === b) {
    return true;
  }
  if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) {
    return false;
  }
  for (let index = 0; index < a.length; index += 1) {
    if (a[index] !== b[index]) {
      return false;
    }
  }
  return true;
}

function uniqueStringList(values) {
  const seen = new Set();
  const result = [];
  for (const value of Array.isArray(values) ? values : []) {
    const normalizedValue = String(value || "").trim();
    if (!normalizedValue || seen.has(normalizedValue)) {
      continue;
    }
    seen.add(normalizedValue);
    result.push(normalizedValue);
  }
  return result;
}

function normalizePosixPath(path) {
  const parts = [];
  for (const part of String(path || "").replace(/\\/g, "/").split("/")) {
    if (!part || part === ".") {
      continue;
    }
    if (part === "..") {
      parts.pop();
      continue;
    }
    parts.push(part);
  }
  return parts.join("/");
}

function resolveTopologyRelativeFile(entry, sourcePath) {
  const relativeSourcePath = String(sourcePath || "").trim();
  const stepPath = String(entry?.step?.path || entry?.source?.path || "").trim();
  if (!relativeSourcePath || !stepPath) {
    return "";
  }
  const stepParts = stepPath.split("/");
  const stepFilename = stepParts.pop();
  const stepDirectory = stepParts.join("/");
  const topologyDirectory = stepDirectory ? `${stepDirectory}/.${stepFilename}` : `.${stepFilename}`;
  return normalizePosixPath(`${topologyDirectory}/${relativeSourcePath}`);
}

function cadRefQueryHasKnownEntry(cadRefs, entries) {
  const cadPaths = new Set();
  for (const cadRef of Array.isArray(cadRefs) ? cadRefs : []) {
    const cadPath = String(parseCadRefToken(cadRef)?.cadPath || "").trim();
    if (cadPath) {
      cadPaths.add(cadPath);
    }
  }
  if (!cadPaths.size) {
    return false;
  }
  return (Array.isArray(entries) ? entries : []).some((entry) => cadPaths.has(cadPathForEntry(entry)));
}

function collectCadRefSelectionRequest(cadRefs, entry) {
  const cadPath = cadPathForEntry(entry);
  const selectors = [];
  let hasMatchingToken = false;
  let hasWholeEntryToken = false;

  if (!cadPath) {
    return {
      hasMatchingToken,
      hasWholeEntryToken,
      selectors,
      needsParts: false,
      needsReferences: false
    };
  }

  for (const cadRef of Array.isArray(cadRefs) ? cadRefs : []) {
    const parsedToken = parseCadRefToken(cadRef);
    if (!parsedToken || parsedToken.cadPath !== cadPath) {
      continue;
    }
    hasMatchingToken = true;
    if (!parsedToken.selectors.length) {
      hasWholeEntryToken = true;
      continue;
    }
    selectors.push(...parsedToken.selectors);
  }

  const normalizedSelectors = sortCadRefSelectors(selectors);
  let needsParts = false;
  let needsReferences = false;
  for (const selector of normalizedSelectors) {
    const parsedSelector = parseCadRefSelector(selector);
    if (entry?.kind === "assembly" && parsedSelector?.selectorType === "occurrence") {
      needsParts = true;
    } else {
      needsReferences = true;
    }
  }

  return {
    hasMatchingToken,
    hasWholeEntryToken,
    selectors: normalizedSelectors,
    needsParts,
    needsReferences
  };
}

function addTokenSelectorsToMap(map, copyText, value, cadPath) {
  const parsedToken = parseCadRefToken(copyText);
  if (!parsedToken || parsedToken.cadPath !== cadPath) {
    return;
  }
  for (const selector of parsedToken.selectors) {
    if (selector && !map.has(selector)) {
      map.set(selector, value);
    }
  }
}

function addReferenceIdSelectorToMap(map, reference, value) {
  const displaySelector = String(reference?.displaySelector || reference?.normalizedSelector || "").trim();
  if (!displaySelector) {
    return;
  }
  const parsedSelector = parseCadRefSelector(displaySelector);
  if (parsedSelector?.canonical && !map.has(parsedSelector.canonical)) {
    map.set(parsedSelector.canonical, value);
  }
  if (reference?.normalizedSelector && !map.has(reference.normalizedSelector)) {
    map.set(reference.normalizedSelector, value);
  }
}

function buildReferenceSelectorMap(references, cadPath) {
  const map = new Map();
  for (const reference of Array.isArray(references) ? references : []) {
    const referenceId = String(reference?.id || "").trim();
    if (!referenceId) {
      continue;
    }
    const value = {
      id: referenceId,
      partId: String(reference?.partId || "").trim()
    };
    addTokenSelectorsToMap(map, reference?.copyText, value, cadPath);
    addReferenceIdSelectorToMap(map, reference, value);
  }
  return map;
}

function buildAssemblyPartSelectorMap(parts, cadPath) {
  const map = new Map();
  for (const part of Array.isArray(parts) ? parts : []) {
    const partId = String(part?.id || "").trim();
    const selector = String(part?.occurrenceId || partId).trim();
    if (!partId || !selector) {
      continue;
    }
    const copyText = buildCadRefToken({
      cadPath,
      selector
    });
    addTokenSelectorsToMap(map, copyText, partId, cadPath);
    addTokenSelectorsToMap(map, selector, partId, cadPath);
  }
  return map;
}

function resolveCadRefSelection({ cadRefs = [], entry = null, references = [], assemblyParts = [], isAssemblyView = false } = {}) {
  const request = collectCadRefSelectionRequest(cadRefs, entry);
  const cadPath = cadPathForEntry(entry);
  const referenceSelectorMap = buildReferenceSelectorMap(references, cadPath);
  const assemblyPartSelectorMap = buildAssemblyPartSelectorMap(assemblyParts, cadPath);
  const selectedReferenceIds = [];
  const selectedPartIds = [];
  const expandedAssemblyPartIds = [];

  for (const selector of request.selectors) {
    const parsedSelector = parseCadRefSelector(selector);
    const canonicalSelector = String(parsedSelector?.canonical || selector || "").trim();
    if (!canonicalSelector) {
      continue;
    }

    if (isAssemblyView && parsedSelector?.selectorType === "occurrence") {
      const partId = assemblyPartSelectorMap.get(canonicalSelector);
      if (partId) {
        selectedPartIds.push(partId);
      }
      continue;
    }

    const reference = referenceSelectorMap.get(canonicalSelector);
    if (!reference) {
      continue;
    }
    selectedReferenceIds.push(reference.id);
    if (isAssemblyView && reference.partId) {
      expandedAssemblyPartIds.push(reference.partId);
    }
  }

  return {
    ...request,
    selectedReferenceIds: uniqueStringList(selectedReferenceIds),
    selectedPartIds: uniqueStringList(selectedPartIds),
    expandedAssemblyPartIds: uniqueStringList(expandedAssemblyPartIds).slice(0, 1)
  };
}

function computeNextSelectionIds(currentIds, selectionId, { multiSelect = false } = {}) {
  const normalizedSelectionId = String(selectionId || "").trim();
  if (!normalizedSelectionId) {
    return [];
  }
  const current = Array.isArray(currentIds) ? currentIds : [];
  if (multiSelect) {
    return current.includes(normalizedSelectionId)
      ? current.filter((id) => id !== normalizedSelectionId)
      : [...current, normalizedSelectionId];
  }
  if (current.length === 1 && current[0] === normalizedSelectionId) {
    return [];
  }
  return [normalizedSelectionId];
}

function buildExplorerMeshAlert(entry, hasMeshData, loadError) {
  const fileRef = fileKey(entry);
  if (!fileRef) {
    return null;
  }

  const sourceFormat = entrySourceFormat(entry);
  const command = buildCadCommand(fileRef, entry);
  const stepArtifactError = sourceFormat === RENDER_FORMAT.STEP && !entry?.stepArtifact?.ok
    ? entry?.stepArtifact?.error
    : null;
  if (stepArtifactError) {
    const code = String(stepArtifactError.code || "").trim();
    const summary = code === "missing_glb"
      ? "STEP artifacts missing"
      : code === "stale_step_topology"
        ? "STEP artifacts stale"
        : "STEP artifacts invalid";
    const regenerateCommand = String(stepArtifactError.regenerateCommand || CAD_BUILD_COMMANDS.step).trim();
    return {
      severity: "error",
      compact: true,
      summary,
      title: summary,
      message: String(stepArtifactError.message || "STEP artifacts are unavailable."),
      command: regenerateCommand ? `${regenerateCommand} ${fileRef}` : command
    };
  }
  const meshSidecarFormat = sourceFormat === RENDER_FORMAT.STL ||
    sourceFormat === RENDER_FORMAT.THREE_MF ||
    sourceFormat === RENDER_FORMAT.GLB;
  const meshSidecarLabel = sourceFormat === RENDER_FORMAT.THREE_MF
    ? "3MF"
    : sourceFormat === RENDER_FORMAT.GLB
      ? "GLB"
      : "STL";
  const reloadResolution = meshSidecarFormat
    ? `Confirm the ${meshSidecarLabel} exists in the repo and reload the page.`
    : "Try reloading the page. If the problem persists, rebuild the render assets for this entry.";
  const missingResolution = meshSidecarFormat
    ? `Confirm the ${meshSidecarLabel} exists in the repo and reload the page.`
    : "Rebuild the CAD assets for this entry, then reload the page.";

  if (loadError) {
    return {
      severity: "error",
      summary: "Mesh load failed",
      title: "Failed to load render mesh",
      message: loadError,
      resolution: reloadResolution,
      command
    };
  }

  if (!hasMeshData) {
    return {
      severity: "error",
      summary: "Mesh unavailable",
      title: "No mesh data is available",
      message: "The selected entry is listed in the CAD catalog but no renderable mesh data could be loaded for it.",
      resolution: missingResolution,
      command
    };
  }

  return null;
}

function buildExplorerDxfAlert(fileRef, hasDxfData, loadError, previewError) {
  if (!fileRef) {
    return null;
  }

  const command = `${CAD_BUILD_COMMANDS.dxf} ${fileRef}`;

  if (loadError) {
    return {
      severity: "error",
      summary: "DXF load failed",
      title: "Failed to load DXF flat pattern",
      message: loadError,
      resolution: "Try reloading the page. If the problem persists, rebuild the CAD assets for this entry.",
      command
    };
  }

  if (previewError) {
    return {
      severity: "warning",
      summary: "DXF 3D preview unavailable",
      title: "Failed to build the DXF 3D preview",
      message: previewError,
      resolution: "The flat pattern can still be shown, but the 3D extrusion preview could not be built from the current DXF geometry.",
      command
    };
  }

  if (!hasDxfData) {
    return {
      severity: "error",
      summary: "DXF unavailable",
      title: "No DXF flat pattern is available",
      message: "The selected entry does not have a ready DXF companion asset for the flat-pattern explorer.",
      resolution: "Rebuild the CAD assets for this entry, then reload the page.",
      command
    };
  }

  return null;
}

export default function CadWorkspace({
  manifestEntries: manifestEntriesProp = [],
  catalogRootName = "",
  catalogRootDir = "",
  manifestRevision = 0
}) {
  const manifestEntries = Array.isArray(manifestEntriesProp) ? manifestEntriesProp : [];
  const [catalogEntries, setCatalogEntries] = useState(manifestEntries);
  const [query, setQuery] = useState("");
  const [expandedDirectoryIds, setExpandedDirectoryIds] = useState(() => new Set());
  const [openTabs, setOpenTabs] = useState([]);
  const [selectedKey, setSelectedKey] = useState("");
  const [dxfThicknessMm, setDxfThicknessMm] = useState(0);
  const [dxfBendSettings, setDxfBendSettings] = useState([]);
  const [referenceQuery, setReferenceQuery] = useState("");
  const [selectedReferenceIds, setSelectedReferenceIds] = useState([]);
  const [hoveredListReferenceId, setHoveredListReferenceId] = useState("");
  const [hoveredModelReferenceId, setHoveredModelReferenceId] = useState("");
  const [selectedPartIds, setSelectedPartIds] = useState([]);
  const [selectedRenderPartIdByAssemblyPartId, setSelectedRenderPartIdByAssemblyPartId] = useState({});
  const [selectedWholeEntryCadRefToken, setSelectedWholeEntryCadRefToken] = useState("");
  const [expandedAssemblyPartIds, setExpandedAssemblyPartIds] = useState([]);
  const [expandedStepTreeNodeIds, setExpandedStepTreeNodeIds] = useState([]);
  const [hiddenPartIds, setHiddenPartIds] = useState([]);
  const [stepClipSettings, setStepClipSettings] = useState(() => normalizeStepClipSettings(DEFAULT_STEP_CLIP_SETTINGS));
  const [hoveredListPartId, setHoveredListPartId] = useState("");
  const [hoveredModelPartId, setHoveredModelPartId] = useState("");
  const [copyStatus, setCopyStatus] = useState("");
  const [stepUpdateInProgress, setStepUpdateInProgress] = useState(false);
  const [screenshotStatus, setScreenshotStatus] = useState("");
  const [persistenceStatus, setPersistenceStatus] = useState("");
  const [motionErrorStatus, setMotionErrorStatus] = useState("");
  const [moveit2ServerLive, setMoveIt2ServerLive] = useState(false);
  const [workspaceLayoutMode, setWorkspaceLayoutMode] = useState(readWorkspaceLayoutMode);
  const [sidebarOpen, setSidebarOpen] = useState(() => (
    shouldCadWorkspaceDefaultFileExplorerOpen(readWorkspaceViewportWidth(), { hasSelectedFile: false })
  ));
  const [sidebarWidth, setSidebarWidth] = useState(DEFAULT_SIDEBAR_WIDTH);
  const [layoutViewportWidth, setLayoutViewportWidth] = useState(readWorkspaceViewportWidth);
  const isDesktop = workspaceLayoutMode === CAD_WORKSPACE_LAYOUT_MODE.DESKTOP;
  const [fileSheetOpenIntent, setFileSheetOpenIntent] = useState(() => (
    shouldCadWorkspaceDefaultFileSettingsOpen(readWorkspaceViewportWidth())
  ));
  const [explorerAlertOpen, setExplorerAlertOpen] = useState(false);
  const [explorerRuntimeAlert, setExplorerRuntimeAlert] = useState(null);
  const [customThemePresets, setCustomThemePresets] = useState(readCustomThemePresets);
  const [themeState, setThemeState] = useState(() => readThemeSettingsState(readCustomThemePresets()));
  const themeSettings = themeState.settings;
  const themePresetId = themeState.presetId;
  const availableThemePresets = useMemo(() => buildAvailableThemePresets(customThemePresets), [customThemePresets]);
  const cadWorkspaceGlassTone = useMemo(() => inferThemeSettingsSceneTone(themeSettings), [themeSettings]);
  const [previewMode, setPreviewMode] = useState(false);
  const [tabToolsWidth, setTabToolsWidth] = useState(DEFAULT_TAB_TOOLS_WIDTH);
  const [drawingTool, setDrawingTool] = useState(DRAWING_TOOL.FREEHAND);
  const [explorerPerspective, setExplorerPerspective] = useState(null);
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
  const [stepModuleTransformDetected, setStepModuleTransformDetected] = useState(false);
  const [stepModuleAnimationState, setStepModuleAnimationState] = useState({
    activeId: "",
    playing: false,
    elapsedSec: 0,
    speed: 1
  });
  const [urdfPosePickerState, setUrdfPosePickerState] = useState(emptyUrdfPosePickerState);
  const [pendingCadRefQueryParams, setPendingCadRefQueryParams] = useState(() => readCadRefQueryParams());
  const [inspectedAssemblyReferenceState, setInspectedAssemblyReferenceState] = useState(null);
  const [inspectedAssemblyReferenceStatus, setInspectedAssemblyReferenceStatus] = useState(REFERENCE_STATUS.IDLE);
  const [, setInspectedAssemblyReferenceError] = useState("");
  const lastPersistenceFailureKeyRef = useRef("");
  const urdfTrajectoryPlaybackRef = useRef({
    frameId: 0,
    token: 0
  });

  const handlePersistenceWriteError = useCallback(({ key }) => {
    const failureKey = String(key || "browser-storage");
    if (lastPersistenceFailureKeyRef.current === failureKey) {
      return;
    }
    lastPersistenceFailureKeyRef.current = failureKey;
    setPersistenceStatus("Browser storage could not save the CAD Explorer session.");
  }, []);

  const entryMap = useMemo(() => {
    const map = new Map();
    for (const entry of catalogEntries) {
      map.set(fileKey(entry), entry);
    }
    return map;
  }, [catalogEntries]);
  const fileSessionNamespace = useMemo(
    () => normalizeFileSessionNamespace(catalogRootDir || catalogRootName),
    [catalogRootDir, catalogRootName]
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
    getCachedMeshState,
    getCachedReferenceState,
    getCachedDxfState,
    getCachedUrdfState,
    cancelMeshLoad,
    cancelDxfLoad,
    cancelUrdfLoad,
    cancelReferenceLoad,
    loadMeshForEntry,
    loadDxfForEntry,
    loadUrdfForEntry,
    loadReferencesForEntry
  } = useCadAssets({
    entryHasMesh,
    entryHasReferences,
    entryHasDxf,
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
        String(entry.name || "").toLowerCase().includes(q) ||
        entry.kind.toLowerCase().includes(q) ||
        fileKey(entry).toLowerCase().includes(q) ||
        String(entry.source?.path || entry.step?.path || "").toLowerCase().includes(q)
      );
    });
  }, [catalogEntries, query]);
  const allEntriesTree = useMemo(
    () => buildSidebarDirectoryTree(catalogEntries, { rootName: catalogRootName }),
    [catalogEntries, catalogRootName]
  );
  const filteredEntriesTree = useMemo(
    () => buildSidebarDirectoryTree(filteredEntries, { rootName: catalogRootName }),
    [filteredEntries, catalogRootName]
  );
  const allDirectoryIds = useMemo(() => collectSidebarDirectoryIds(allEntriesTree), [allEntriesTree]);

  const selectedEntry = entryMap.get(selectedKey) ?? null;
  const explicitFileParam = readCadParam();
  const missingFileRef = explicitFileParam && !findEntryByUrlPath(catalogEntries, explicitFileParam)
    ? explicitFileParam
    : "";
  const selectedEntrySourceFormat = entrySourceFormat(selectedEntry);
  const selectedFileSheetKind = fileSheetKindForEntry(selectedEntry);
  const isStepView = selectedEntrySourceFormat === RENDER_FORMAT.STEP;
  const isAssemblyView = selectedEntry?.kind === "assembly";
  const isUrdfView = isRobotRenderFormat(selectedEntrySourceFormat);
  const selectedStepModuleUrl = isStepView ? String(selectedEntry?.assets?.stepModule?.url || "").trim() : "";
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
  const selectedEntryHasMesh = entryHasMesh(selectedEntry);
  const selectedEntryHasUrdf = entryHasUrdf(selectedEntry);
  const selectedEntryHasReferences = entryHasReferences(selectedEntry);
  const selectedEntryHasDxf = entryHasDxf(selectedEntry);
  const selectedMeshHash = String(
    selectedEntry?.kind === "assembly"
      ? [entryAssetHash(selectedEntry, "topology"), entryAssetHash(selectedEntry, "glb")].filter(Boolean).join(":")
      : entryAssetHash(selectedEntry, meshAssetKeyForEntry(selectedEntry))
  );
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
  const selectedUrdfMatches =
    !!urdfState &&
    !!selectedEntry &&
    urdfState.file === fileKey(selectedEntry) &&
    urdfState.urdfHash === entryUrdfAssetHash(selectedEntry);
  const selectedUrdfData = selectedUrdfMatches ? urdfState.urdfData : null;
  const selectedUrdfMeshes = selectedUrdfMatches ? urdfState.meshesByUrl : null;
  const selectedDxfData = selectedDxfMatches ? dxfState.dxfData : null;
  const selectedDxfFileRef = selectedEntrySourceFormat === RENDER_FORMAT.DXF
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
      setStepModuleParameterValues(normalizeStepModuleParameterValues(
        definition,
        restoredStepModuleState?.parameterValues || definition.defaultParameterValues
      ));
      setStepModuleEnabled(restoredStepModuleState ? restoredStepModuleState.enabled !== false : true);
      setStepModuleAnimationState(restoredStepModuleState?.animationState
        ? {
            ...defaultAnimationState,
            ...restoredStepModuleState.animationState,
            activeId: restoredStepModuleState.animationState.activeId || defaultAnimationState.activeId,
            playing: false
          }
        : defaultAnimationState);
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
    });

    return () => {
      cancelled = true;
    };
  }, [fileSessionNamespace, selectedEntry, selectedStepModuleCadPath, selectedStepModuleUrl]);

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
  const selectedMeshData = isRobotRenderFormat(selectedEntrySourceFormat)
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
    loop: selectedStepModuleActiveAnimation?.loop !== false
  }), [selectedStepModuleActiveAnimation, stepModuleAnimationState]);
  const selectedStepModuleRuntime = useMemo(() => {
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
  const handleStepModuleTransformDetectedChange = useCallback((detected) => {
    const nextDetected = detected === true;
    setStepModuleTransformDetected((current) => (
      current === nextDetected ? current : nextDetected
    ));
  }, []);
  useEffect(() => {
    setStepModuleTransformDetected(false);
  }, [selectedKey, selectedStepModuleUrl]);
  useEffect(() => {
    if (!selectedStepModuleRuntime) {
      setStepModuleTransformDetected(false);
    }
  }, [selectedStepModuleRuntime]);
  const stepModuleTreeSelectionDisabled = Boolean(selectedStepModuleRuntime && stepModuleTransformDetected);
  const stepModuleTreeSelectionDisabledReason = stepModuleTreeSelectionDisabled
    ? STEP_MODULE_TRANSFORM_SELECTION_DISABLED_REASON
    : "";

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

  const handleResetStepModuleParameters = useCallback(() => {
    if (!selectedStepModuleDefinition) {
      return;
    }
    setStepModuleParameterValues(normalizeStepModuleParameterValues(
      selectedStepModuleDefinition,
      selectedStepModuleDefinition.defaultParameterValues
    ));
    setStepModuleAnimationState(buildDefaultStepModuleAnimationState(selectedStepModuleDefinition));
  }, [selectedStepModuleDefinition]);

  const handleStepModuleAnimationSelect = useCallback((animationId) => {
    const animation = findStepModuleAnimation(selectedStepModuleDefinition, animationId);
    setStepModuleAnimationState((current) => ({
      ...current,
      activeId: animation?.id || "",
      playing: false,
      elapsedSec: 0
    }));
  }, [selectedStepModuleDefinition]);

  const handleStepModuleAnimationPlayToggle = useCallback(() => {
    setStepModuleAnimationState((current) => {
      const animation = findStepModuleAnimation(selectedStepModuleDefinition, current.activeId);
      if (!animation) {
        return current;
      }
      const duration = Math.max(Number(animation.duration) || 0, 0.001);
      const elapsedSec = current.elapsedSec >= duration ? 0 : current.elapsedSec;
      return {
        ...current,
        activeId: animation.id,
        elapsedSec,
        playing: !current.playing
      };
    });
  }, [selectedStepModuleDefinition]);

  const handleStepModuleAnimationReset = useCallback(() => {
    setStepModuleAnimationState((current) => ({
      ...current,
      elapsedSec: 0,
      playing: false
    }));
  }, []);

  const handleStepModuleAnimationScrub = useCallback((elapsedSec) => {
    const duration = Math.max(Number(selectedStepModuleActiveAnimation?.duration) || 1, 0.001);
    setStepModuleAnimationState((current) => ({
      ...current,
      elapsedSec: clampNumber(elapsedSec, 0, duration)
    }));
  }, [selectedStepModuleActiveAnimation]);

  const handleStepModuleAnimationSpeedChange = useCallback((speed) => {
    setStepModuleAnimationState((current) => ({
      ...current,
      speed: clampNumber(speed, 0.1, 5)
    }));
  }, []);

  const handleStepModuleEnabledChange = useCallback((enabled) => {
    const nextEnabled = enabled !== false;
    setStepModuleEnabled(nextEnabled);
    if (!nextEnabled) {
      setStepModuleAnimationState((current) => ({
        ...current,
        playing: false
      }));
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

    let frameId = 0;
    let previousTimeMs = animationNowMs();
    const tick = (timeMs) => {
      const deltaSec = Math.max((timeMs - previousTimeMs) / 1000, 0);
      previousTimeMs = timeMs;
      setStepModuleAnimationState((current) => {
        if (!current.playing || current.activeId !== selectedStepModuleActiveAnimation.id) {
          return current;
        }
        const duration = Math.max(Number(selectedStepModuleActiveAnimation.duration) || 1, 0.001);
        const speed = clampNumber(current.speed, 0.1, 5);
        let elapsedSec = current.elapsedSec + (deltaSec * speed);
        let playing = current.playing;
        if (selectedStepModuleActiveAnimation.loop !== false) {
          elapsedSec %= duration;
        } else if (elapsedSec >= duration) {
          elapsedSec = duration;
          playing = false;
        }
        return {
          ...current,
          elapsedSec,
          speed,
          playing
        };
      });
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
      return;
    }
    const duration = Math.max(Number(animation.duration) || 1, 0.001);
    const elapsedSec = clampNumber(stepModuleAnimationState.elapsedSec, 0, duration);
    const progress = duration > 0 ? clampNumber(elapsedSec / duration, 0, 1) : 0;
    setStepModuleParameterValues((current) => {
      const normalizedCurrent = normalizeStepModuleParameterValues(selectedStepModuleDefinition, current);
      const nextValues = { ...normalizedCurrent };
      const set = (parameterId, value) => {
        const id = String(parameterId || "").trim();
        const parameter = selectedStepModuleDefinition.parameterMap?.[id];
        if (!parameter) {
          return;
        }
        nextValues[id] = normalizeParameterValue(parameter, value);
      };
      try {
        animation.update({
          elapsed: elapsedSec,
          elapsedSec,
          duration,
          progress,
          cycle: duration > 0 ? elapsedSec / duration : 0,
          loop: animation.loop !== false,
          params: normalizedCurrent,
          set
        });
      } catch (error) {
        console.error("STEP animation update failed", error);
      }
      return shallowObjectValuesEqual(current, nextValues) ? current : nextValues;
    });
  }, [
    selectedStepModuleActiveAnimation,
    selectedStepModuleDefinition,
    stepModuleEnabled,
    stepModuleAnimationState.elapsedSec
  ]);
  const assemblyRoot = selectedAssemblyStructureReady
    ? selectedMeshData?.assemblyRoot || null
    : null;
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
  const assemblyCurrentNodeId = expandedAssemblyPartIds[expandedAssemblyPartIds.length - 1] || "root";
  const assemblyCurrentNode = useMemo(
    () => findAssemblyNode(assemblyRoot, assemblyCurrentNodeId) || assemblyRoot,
    [assemblyCurrentNodeId, assemblyRoot]
  );
  const assemblyParts = useMemo(() => {
    return String(assemblyCurrentNode?.nodeType || "").trim() === "assembly"
      ? (Array.isArray(assemblyCurrentNode?.children) ? assemblyCurrentNode.children : []).map((node) => ({
        ...node,
        leafPartIds: descendantLeafPartIds(node)
      }))
      : [];
  }, [assemblyCurrentNode]);
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
  const dxfExplorerLoading =
    !!selectedEntry &&
    dxfStatus !== ASSET_STATUS.ERROR &&
    (!selectedDxfMatches || dxfStatus === ASSET_STATUS.LOADING);
  const urdfExplorerLoading =
    !!selectedEntry &&
    urdfStatus !== ASSET_STATUS.ERROR &&
    (!selectedUrdfMatches || urdfStatus === ASSET_STATUS.LOADING);
  const stepArtifactInvalid =
    effectiveRenderFormat === RENDER_FORMAT.STEP &&
    selectedEntry?.stepArtifact &&
    !selectedEntry.stepArtifact.ok;
  const stepExplorerLoading =
    !!selectedEntry &&
    !stepArtifactInvalid &&
    status !== ASSET_STATUS.ERROR &&
    (!selectedMeshMatches || status === ASSET_STATUS.LOADING);
  const explorerLoading = effectiveRenderFormat === RENDER_FORMAT.DXF
    ? dxfExplorerLoading
    : isRobotRenderFormat(effectiveRenderFormat)
      ? urdfExplorerLoading
      : stepExplorerLoading;
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
  const explorerLoadingLabel = effectiveRenderFormat === RENDER_FORMAT.DXF
    ? selectedEntry && !selectedEntryHasDxf
      ? "Generating DXF preview..."
      : "Loading DXF preview..."
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
              : selectedEntry && !selectedEntryHasMesh
                ? "Generating CAD assets..."
                : "Loading CAD...";
  const explorerAlert = useMemo(() => {
    if (explorerRuntimeAlert?.blocking) {
      return explorerRuntimeAlert;
    }
    if (!selectedEntry || explorerLoading) {
      return null;
    }
    if (effectiveRenderFormat === RENDER_FORMAT.DXF) {
      return buildExplorerDxfAlert(
        fileKey(selectedEntry),
        !!selectedDxfData,
        dxfStatus === ASSET_STATUS.ERROR ? dxfError : "",
        selectedDxfPreviewError
      );
    }
    if (isRobotRenderFormat(effectiveRenderFormat)) {
      return buildExplorerMeshAlert(
        selectedEntry,
        !!selectedMeshData,
        urdfStatus === ASSET_STATUS.ERROR ? urdfError : selectedUrdfPreviewError
      ) || explorerRuntimeAlert;
    }
    const meshAlert = buildExplorerMeshAlert(
      selectedEntry,
      !!selectedMeshData,
      status === ASSET_STATUS.ERROR ? error : ""
    );
    return meshAlert || explorerRuntimeAlert;
  }, [
    dxfError,
    selectedDxfPreviewError,
    dxfStatus,
    effectiveRenderFormat,
    error,
    selectedDxfData,
    selectedEntry,
    selectedMeshData,
    selectedUrdfPreviewError,
    status,
    urdfError,
    urdfStatus,
    explorerLoading,
    explorerRuntimeAlert
  ]);
  const explorerAlertKey = explorerAlert
    ? [
      fileKey(selectedEntry),
      explorerAlert.severity,
      explorerAlert.summary,
      explorerAlert.title
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
  const explorerInAssemblyMode =
    isAssemblyView &&
    String(assemblyCurrentNode?.nodeType || "assembly").trim() === "assembly";
  const explorerMode = explorerInAssemblyMode ? "assembly" : "part";
  const drawModeActive = selectedEntrySourceFormat === RENDER_FORMAT.STEP && tabToolMode === TAB_TOOL_MODE.DRAW;
  const selectionCountBase = selectedPartIds.length + selectedReferenceIds.length;

  const selectedReferenceIdsRef = useRef(selectedReferenceIds);
  const selectedPartIdsRef = useRef(selectedPartIds);
  const selectedEntryBuildSnapshotRef = useRef({
    fileRef: "",
    stepHash: ""
  });
  const initializedStepTreeKeyRef = useRef("");
  const drawingStrokesRef = useRef(drawingStrokes);
  const drawingUndoStackRef = useRef(drawingUndoStack);
  const drawingRedoStackRef = useRef(drawingRedoStack);
  const explorerRef = useRef(null);
  const previewUiStateRef = useRef(null);
  const panelResizeStateRef = useRef(null);
  const fileSessionSaveTimerRef = useRef(0);
  const openTabsRef = useRef(openTabs);
  const activePerspectiveRef = useRef(null);
  const tabToolsResizeStateRef = useRef(null);
  const selectedFileSheetKeyRef = useRef("");
  const cadWorkspaceSessionBootstrappedRef = useRef(false);

  useEffect(() => {
    openTabsRef.current = openTabs;
  }, [openTabs]);

  const tabToolsOpen = fileSheetOpenIntent;

  const setTabToolsOpen = useCallback((value) => {
    setFileSheetOpenIntent((current) => (
      typeof value === "function" ? value(current) : value
    ));
  }, []);
  const desktopFileSheetOpen = isDesktop && tabToolsOpen && !!selectedFileSheetKind && !previewMode;
  const effectiveSidebarOpen = sidebarOpen && !previewMode;
  const desktopSidebarOpen = isDesktop && effectiveSidebarOpen && !previewMode;

  const setThemeMenuOpen = useCallback(() => {}, []);

  const updateThemeSettings = useCallback((updater) => {
    setThemeState((current) => {
      const next = typeof updater === "function" ? updater(current.settings) : updater;
      const settings = normalizeThemeSettings(next);
      return {
        presetId: getAvailableThemePresetIdForSettings(settings, customThemePresets) || "",
        settings
      };
    });
  }, [customThemePresets]);

  const readSystemDefaultThemeState = useCallback(() => {
    const colorSchemeQuery = typeof window !== "undefined"
      ? window.matchMedia?.("(prefers-color-scheme: dark)")
      : null;
    const presetId = resolveSystemThemePresetId({ prefersDark: colorSchemeQuery?.matches === true });
    const preset = availableThemePresets.find((candidate) => candidate.id === presetId);
    return {
      presetId,
      settings: normalizeThemeSettings(preset?.settings)
    };
  }, [availableThemePresets]);

  const handleResetThemeSettings = useCallback(() => {
    setThemeState(readSystemDefaultThemeState());
  }, [readSystemDefaultThemeState]);

  const handleSaveCustomThemePreset = useCallback((themeName) => {
    const savedPreset = saveCustomThemePreset(themeName, themeSettings, { onWriteError: handlePersistenceWriteError });
    if (!savedPreset) {
      return null;
    }
    const nextCustomThemePresets = readCustomThemePresets();
    setCustomThemePresets(nextCustomThemePresets);
    setThemeState({
      presetId: savedPreset.id,
      settings: normalizeThemeSettings(savedPreset.settings)
    });
    return savedPreset;
  }, [handlePersistenceWriteError, themeSettings]);

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
      return {
        ...current,
        presetId: getAvailableThemePresetIdForSettings(current.settings, nextCustomThemePresets) || ""
      };
    });
    return true;
  }, [handlePersistenceWriteError]);

  const handleExplorerAlertChange = useCallback((nextAlert) => {
    setExplorerRuntimeAlert(nextAlert || null);
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
      latestWidth: nextWidth,
      animationFrame: 0
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
      if (!current && nextOpen) {
        setSidebarWidth((currentWidth) => {
          const numericWidth = Number(currentWidth);
          return Number.isFinite(numericWidth) && numericWidth > DEFAULT_SIDEBAR_WIDTH
            ? currentWidth
            : DEFAULT_SIDEBAR_WIDTH;
        });
      }
      return nextOpen;
    });
  }, []);

  const handleStartFileSheetResize = useCallback((event) => {
    if (event.button !== 0) {
      return;
    }
    const rightSheetOpen = !previewMode && tabToolsOpen && !!selectedFileSheetKind;
    if (!isDesktop || !rightSheetOpen) {
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

  const buildActiveTabSnapshot = useCallback(() => {
    return cloneTabSnapshot({
      dxfThicknessMm,
      referenceQuery,
      selectedReferenceIds,
      selectedPartIds,
      expandedAssemblyPartIds,
      expandedStepTreeNodeIds,
      hiddenPartIds,
      stepClipSettings,
      perspective: activePerspectiveRef.current,
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
    expandedAssemblyPartIds,
    expandedStepTreeNodeIds,
    hiddenPartIds,
    referenceQuery,
    selectedPartIds,
    selectedReferenceIds,
    stepClipSettings,
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
    return createFileSessionSnapshot({
      fileKey: targetFileKey,
      entry: targetEntry,
      slices: {
        theme: {
          presetId: themePresetId,
          settings: themeSettings
        },
        tab: buildActiveTabSnapshot(),
        dxf: {
          thicknessMm: dxfThicknessMm,
          bendSettings: dxfBendSettings
        },
        stepModule: {
          enabled: stepModuleEnabled,
          parameterValues: stepModuleParameterValues,
          animationState: stepModuleAnimationState
        },
        urdf: {
          jointValues: targetUrdfJointValues,
          motionState: targetUrdfMotionState
        }
      }
    });
  }, [
    buildActiveTabSnapshot,
    dxfBendSettings,
    dxfThicknessMm,
    jointValuesByFileRef,
    selectedEntry,
    stepModuleAnimationState,
    stepModuleEnabled,
    stepModuleParameterValues,
    themePresetId,
    themeSettings,
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

  const applyEntrySessionState = useCallback((key, fileSessionState = null) => {
    const normalizedKey = String(key || "").trim();
    if (!normalizedKey) {
      return;
    }
    const sessionState = fileSessionState || readEntrySessionState(normalizedKey);
    const themeSlice = sessionState?.slices?.theme || null;
    if (themeSlice) {
      setThemeState({
        presetId: themeSlice.presetId,
        settings: normalizeThemeSettings(themeSlice.settings)
      });
    } else {
      setThemeState(readSystemDefaultThemeState());
    }

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
  }, [readEntrySessionState, readSystemDefaultThemeState]);

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
    const nextPerspective = clonePerspectiveSnapshot(nextTab.perspective);
    selectedFileSheetKeyRef.current = fileSheetSelectionKeyForTab(nextTab.key);
    setDxfThicknessMm(nextTab.dxfThicknessMm);
    setReferenceQuery(nextTab.referenceQuery);
    selectedReferenceIdsRef.current = nextTab.selectedReferenceIds;
    setSelectedReferenceIds(nextTab.selectedReferenceIds);
    selectedPartIdsRef.current = nextTab.selectedPartIds;
    setSelectedPartIds(nextTab.selectedPartIds);
    setSelectedRenderPartIdByAssemblyPartId({});
    setSelectedWholeEntryCadRefToken("");
    setExpandedAssemblyPartIds(nextTab.expandedAssemblyPartIds);
    setExpandedStepTreeNodeIds(nextTab.expandedStepTreeNodeIds);
    setHiddenPartIds(nextTab.hiddenPartIds);
    setStepClipSettings(nextTab.stepClipSettings);
    setHoveredListReferenceId("");
    setHoveredModelReferenceId("");
    setHoveredListPartId("");
    setHoveredModelPartId("");
    setCopyStatus("");
    setScreenshotStatus("");
    setTabToolMode(nextTab.tabToolMode);
    setDrawingTool(nextTab.drawingTool);
    activePerspectiveRef.current = nextPerspective;
    setExplorerPerspective(nextPerspective);
    setDrawingStrokes(nextTab.drawingStrokes);
    setDrawingUndoStack(nextTab.drawingUndoStack);
    setDrawingRedoStack(nextTab.drawingRedoStack);
    setSelectedKey(nextTab.key);
  }, [fileSheetSelectionKeyForTab]);

  const resetActiveWorkspace = useCallback(() => {
    selectedReferenceIdsRef.current = [];
    selectedPartIdsRef.current = [];
    setSelectedWholeEntryCadRefToken("");
    setDxfThicknessMm(0);
    setDxfBendSettings([]);
    setReferenceQuery("");
    setSelectedReferenceIds([]);
    setSelectedPartIds([]);
    setSelectedRenderPartIdByAssemblyPartId({});
    setExpandedAssemblyPartIds([]);
    setExpandedStepTreeNodeIds([]);
    setHiddenPartIds([]);
    setStepClipSettings(normalizeStepClipSettings(DEFAULT_STEP_CLIP_SETTINGS));
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
    setExplorerPerspective(null);
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
    const cachedDxfState = nextEntry ? getCachedDxfState(nextEntry) : null;
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

    if (!entryHasDxf(nextEntry)) {
      setDxfState(null);
      setDxfStatus(ASSET_STATUS.PENDING);
      setDxfError("");
    } else if (cachedDxfState) {
      setDxfState(cachedDxfState);
      setDxfStatus(ASSET_STATUS.READY);
      setDxfError("");
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
    if (!selectedKey && shouldCadWorkspaceDefaultFileSettingsOpen(readWorkspaceViewportWidth())) {
      setTabToolsOpen(true);
    }
  }, [
    applyEntrySessionState,
    applyTabRecord,
    buildActiveTabSnapshot,
    drawingTool,
    entryMap,
    flushActiveFileSession,
    getCachedDxfState,
    getCachedMeshState,
    getCachedReferenceState,
    getCachedUrdfState,
    readEntrySessionState,
    selectedKey,
    setTabToolsOpen,
    setDxfError,
    setDxfState,
    setDxfStatus,
    setUrdfError,
    setUrdfState,
    setUrdfStatus,
    tabToolMode,
    upsertTabRecord
  ]);

  useCadWorkspaceSession({
    manifestEntries,
    fileKey,
    cadWorkspaceSessionBootstrappedRef,
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
    resetActiveWorkspace,
    writeCadParam,
    readEntrySessionState,
    applyEntrySessionState
  });

  useEffect(() => {
    if (!selectedEntry || typeof window === "undefined") {
      return undefined;
    }
    clearFileSessionSaveTimer();
    fileSessionSaveTimerRef.current = window.setTimeout(() => {
      fileSessionSaveTimerRef.current = 0;
      writeFileSessionForEntry(selectedEntry);
    }, 180);
    return () => {
      clearFileSessionSaveTimer();
    };
  }, [clearFileSessionSaveTimer, selectedEntry, writeFileSessionForEntry]);

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
    const colorSchemeQuery = window.matchMedia?.("(prefers-color-scheme: dark)");
    const applySystemTheme = () => {
      applyColorSchemeToDocument(DEFAULT_COLOR_SCHEME_ID, document.documentElement, {
        prefersDark: colorSchemeQuery?.matches === true
      });
    };

    applySystemTheme();

    colorSchemeQuery?.addEventListener?.("change", applySystemTheme);
    return () => {
      colorSchemeQuery?.removeEventListener?.("change", applySystemTheme);
    };
  }, []);

  useEffect(() => {
    const colorSchemeQuery = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!colorSchemeQuery) {
      return undefined;
    }

    const applySystemThemePreset = () => {
      setThemeState((current) => {
        const activePresetId = getThemePresetIdForSettings(current.settings);
        if (activePresetId !== "light" && activePresetId !== "dark") {
          return current;
        }

        const nextState = readSystemDefaultThemeState();
        return nextState.presetId === current.presetId ? current : nextState;
      });
    };

    colorSchemeQuery.addEventListener?.("change", applySystemThemePreset);
    return () => {
      colorSchemeQuery.removeEventListener?.("change", applySystemThemePreset);
    };
  }, [readSystemDefaultThemeState]);

  useEffect(() => {
    writeCustomThemePresetLibrary(customThemePresets, {
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
      if (event.key !== THEME_STORAGE_KEY) {
        return;
      }
      try {
        const nextCustomThemePresets = readCustomThemePresets();
        setCustomThemePresets(nextCustomThemePresets);
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
    const stepHash = String(selectedEntry?.step?.hash || entryAssetHash(selectedEntry, "topology") || "").trim();
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
    setExplorerAlertOpen(false);
  }, [explorerAlertKey]);

  useEffect(() => {
    setExplorerRuntimeAlert(null);
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
    hasSelectedFile: !!selectedEntry,
    setLayoutMode: setWorkspaceLayoutMode,
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
    setCatalogEntries(manifestEntries);
  }, [manifestEntries]);

  useEffect(() => {
    if (!catalogEntries.length) {
      return;
    }
    pruneFileSessionState(
      fileSessionNamespace,
      catalogEntries.map((entry) => fileKey(entry)),
      { onWriteError: handlePersistenceWriteError }
    );
  }, [catalogEntries, fileSessionNamespace, handlePersistenceWriteError]);

  useEffect(() => {
    setOpenTabs((current) => {
      const next = current.filter((tab) => entryMap.has(tab.key));
      return next.length === current.length ? current : next;
    });
  }, [entryMap]);

  useEffect(() => {
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
  }, [allDirectoryIds]);

  useEffect(() => {
    const directoryId = sidebarDirectoryIdForEntry(selectedEntry);
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
  }, [selectedEntry]);

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
  const selectedStepPartRootActive = !isAssemblyView && selectedPartIds.includes(STEP_MODEL_ROOT_ID);
  const plainStepReferencePickingEnabled =
    effectiveRenderFormat === RENDER_FORMAT.STEP &&
    selectedEntryHasReferences &&
    !isAssemblyView;
  const topLevelReferenceSelectionActive =
    pendingCadRefQueryParams.length > 0 ||
    selectedStepPartRootActive ||
    plainStepReferencePickingEnabled;
  const referenceLoadingEnabled =
    pendingCadRefQueryParams.length > 0 ||
    plainStepReferencePickingEnabled ||
    selectedStepPartRootActive;

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
    if (effectiveRenderFormat !== RENDER_FORMAT.DXF || !previewMode) {
      return;
    }
    previewUiStateRef.current = null;
    setPreviewMode(false);
  }, [effectiveRenderFormat, previewMode]);

  const {
    inspectedAssemblyPartId,
    inspectedAssemblyPart,
    isInspectingAssemblyPart,
    activeReferenceMap,
    inspectedAssemblyPartReferences,
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
    expandedAssemblyPartIds,
    inspectedAssemblyPartTopologyReferences: inspectedAssemblyReferenceState?.references || [],
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
    setExpandedAssemblyPartIds,
    setHiddenPartIds,
    setHoveredListPartId,
    setHoveredModelPartId
  });

  useEffect(() => {
    const rootId = String(stepTreeRoot?.id || "").trim();
    if (!rootId) {
      initializedStepTreeKeyRef.current = "";
      setExpandedStepTreeNodeIds((current) => (current.length ? [] : current));
      return;
    }
    const validIds = new Set(validAssemblySelectionIds);
    const treeKey = `${selectedKey}:${rootId}`;
    const shouldInitializeRoot =
      initializedStepTreeKeyRef.current !== treeKey &&
      stepTreeNodeChildren(stepTreeRoot).length > 0;
    initializedStepTreeKeyRef.current = treeKey;
    setExpandedStepTreeNodeIds((current) => {
      const filtered = current.filter((id) => validIds.has(id));
      if (shouldInitializeRoot && !filtered.length) {
        return [rootId];
      }
      return orderedStringListEqual(filtered, current) ? current : filtered;
    });
  }, [selectedKey, stepTreeRoot, validAssemblySelectionIds]);

  const inspectedAssemblyPartEntry = useMemo(() => {
    const partFileRef = resolveTopologyRelativeFile(
      selectedEntry,
      inspectedAssemblyPart?.sourcePath || inspectedAssemblyPart?.partSourcePath
    );
    return partFileRef ? entryMap.get(partFileRef) || null : null;
  }, [entryMap, inspectedAssemblyPart?.partSourcePath, inspectedAssemblyPart?.sourcePath, selectedEntry]);

  useEffect(() => {
    let cancelled = false;

    if (!isAssemblyView || !inspectedAssemblyPartId || !isInspectingAssemblyPart) {
      setInspectedAssemblyReferenceState(null);
      setInspectedAssemblyReferenceStatus(REFERENCE_STATUS.IDLE);
      setInspectedAssemblyReferenceError("");
      return () => {
        cancelled = true;
      };
    }

    if (!inspectedAssemblyPartEntry && String(inspectedAssemblyPart?.sourceKind || "") === "native" && entryHasReferences(selectedEntry)) {
      const occurrenceId = String(inspectedAssemblyPart?.occurrenceId || inspectedAssemblyPart?.id || "").trim();
      const cachedBundle = loadRenderSelectorBundle(entrySelectorTopologyAssetUrl(selectedEntry));
      setInspectedAssemblyReferenceStatus(REFERENCE_STATUS.LOADING);
      setInspectedAssemblyReferenceError("");
      cachedBundle.then((bundle) => {
        if (cancelled) {
          return;
        }
        const nextReferenceState = buildNormalizedReferenceState(selectedEntry, bundle, {
          copyCadPath: cadPathForEntry(selectedEntry),
          partId: inspectedAssemblyPart.id
        });
        const references = nextReferenceState.references
          .filter((reference) => String(reference?.occurrenceId || "").trim() === occurrenceId)
          .map((reference) => ({ ...reference, partId: inspectedAssemblyPart.id }));
        setInspectedAssemblyReferenceState({
          ...nextReferenceState,
          references
        });
        setInspectedAssemblyReferenceStatus(references.length ? REFERENCE_STATUS.READY : REFERENCE_STATUS.DISABLED);
        setInspectedAssemblyReferenceError(references.length ? "" : "No topology references are available for this component");
      }).catch((loadError) => {
        if (cancelled) {
          return;
        }
        setInspectedAssemblyReferenceState(null);
        setInspectedAssemblyReferenceStatus(REFERENCE_STATUS.ERROR);
        setInspectedAssemblyReferenceError(loadError instanceof Error ? loadError.message : String(loadError));
      });
      return () => {
        cancelled = true;
      };
    }

    if (!inspectedAssemblyPartEntry) {
      setInspectedAssemblyReferenceState(null);
      setInspectedAssemblyReferenceStatus(REFERENCE_STATUS.DISABLED);
      setInspectedAssemblyReferenceError("");
      return () => {
        cancelled = true;
      };
    }

    if (!entryHasReferences(inspectedAssemblyPartEntry)) {
      setInspectedAssemblyReferenceState(null);
      setInspectedAssemblyReferenceStatus(REFERENCE_STATUS.DISABLED);
      setInspectedAssemblyReferenceError("");
      return () => {
        cancelled = true;
      };
    }

    const transform = Array.isArray(inspectedAssemblyPart?.transform) && inspectedAssemblyPart.transform.length === 16
      ? inspectedAssemblyPart.transform.map((value) => Number(value))
      : null;
    const sourceRootOccurrenceId = String(inspectedAssemblyPart?.sourceRootOccurrenceId || "").trim();
    const targetRootOccurrenceId = String(
      inspectedAssemblyPart?.sourceRootTargetOccurrenceId ||
      inspectedAssemblyPart?.occurrenceId ||
      inspectedAssemblyPart?.id ||
      ""
    ).trim();
    const sourceOccurrenceId = String(inspectedAssemblyPart?.sourceOccurrenceId || "").trim();
    const remapOccurrencePrefix = sourceRootOccurrenceId && targetRootOccurrenceId
      ? {
        sourceRootOccurrenceId,
        targetRootOccurrenceId,
        sourceOccurrenceId
      }
      : null;
    const cachedBundle = loadRenderSelectorBundle(entrySelectorTopologyAssetUrl(inspectedAssemblyPartEntry));

    setInspectedAssemblyReferenceStatus(REFERENCE_STATUS.LOADING);
    setInspectedAssemblyReferenceError("");

    cachedBundle.then((bundle) => {
      if (cancelled) {
        return;
      }
      const nextReferenceState = buildNormalizedReferenceState(inspectedAssemblyPartEntry, bundle, {
        copyCadPath: cadPathForEntry(selectedEntry) || cadPathForEntry(inspectedAssemblyPartEntry),
        partId: inspectedAssemblyPart.id,
        transform,
        remapOccurrenceId: remapOccurrencePrefix
          ? ""
          : String(inspectedAssemblyPart?.occurrenceId || inspectedAssemblyPart?.id || "").trim(),
        remapOccurrencePrefix
      });
      setInspectedAssemblyReferenceState(nextReferenceState);
      setInspectedAssemblyReferenceStatus(
        nextReferenceState.disabledReason ? REFERENCE_STATUS.DISABLED : REFERENCE_STATUS.READY
      );
      setInspectedAssemblyReferenceError(nextReferenceState.disabledReason || "");
    }).catch((loadError) => {
      if (cancelled) {
        return;
      }
      setInspectedAssemblyReferenceState(null);
      setInspectedAssemblyReferenceStatus(REFERENCE_STATUS.ERROR);
      setInspectedAssemblyReferenceError(loadError instanceof Error ? loadError.message : String(loadError));
    });

    return () => {
      cancelled = true;
    };
  }, [
    inspectedAssemblyPart,
    inspectedAssemblyPartEntry,
    inspectedAssemblyPartId,
    isInspectingAssemblyPart,
    isAssemblyView,
    selectedEntry
  ]);

  const isFaceReference = useCallback((reference) => (
    String(reference?.selectorType || "").trim() === "face"
  ), []);
  const isEdgeReference = useCallback((reference) => (
    String(reference?.selectorType || "").trim() === "edge"
  ), []);
  const referencePartId = useCallback((reference) => {
    const explicitPartId = String(reference?.partId || "").trim();
    if (explicitPartId) {
      return explicitPartId;
    }
    return parseAssemblyPartReferenceSelectionId(reference?.id)?.partId || "";
  }, []);

  const effectiveInspectedAssemblyPartReferences = useMemo(() => {
    if (!isAssemblyView || !inspectedAssemblyPartId) {
      return inspectedAssemblyPartReferences;
    }
    const topologyReferences = (Array.isArray(visibleReferences) ? visibleReferences : [])
      .filter((reference) => {
        const partId = referencePartId(reference);
        if (!partId || partId !== inspectedAssemblyPartId) {
          return false;
        }
        return isFaceReference(reference) || isEdgeReference(reference);
      });
    if (topologyReferences.length) {
      return topologyReferences;
    }
    return inspectedAssemblyPartReferences;
  }, [
    inspectedAssemblyPartId,
    inspectedAssemblyPartReferences,
    isAssemblyView,
    isEdgeReference,
    isFaceReference,
    referencePartId,
    visibleReferences
  ]);

  const effectiveVisibleReferences = useMemo(() => {
    if (isAssemblyView && isInspectingAssemblyPart) {
      return effectiveInspectedAssemblyPartReferences;
    }
    return visibleReferences;
  }, [effectiveInspectedAssemblyPartReferences, isAssemblyView, isInspectingAssemblyPart, visibleReferences]);
  const effectiveSelectorRuntime = useMemo(() => {
    if (isAssemblyView && isInspectingAssemblyPart) {
      return inspectedAssemblyReferenceState?.selectorRuntime || null;
    }
    return selectedSelectorRuntime;
  }, [inspectedAssemblyReferenceState?.selectorRuntime, isAssemblyView, isInspectingAssemblyPart, selectedSelectorRuntime]);

  const effectiveActiveReferenceMap = useMemo(() => {
    const map = new Map(activeReferenceMap);
    for (const reference of effectiveVisibleReferences) {
      const referenceId = String(reference?.id || "").trim();
      if (referenceId) {
        map.set(referenceId, reference);
      }
    }
    return map;
  }, [activeReferenceMap, effectiveVisibleReferences]);

  const explorerPickableReferences = useMemo(() => {
    if (explorerInAssemblyMode || stepModuleTreeSelectionDisabled) {
      return [];
    }
    return effectiveVisibleReferences;
  }, [effectiveVisibleReferences, explorerInAssemblyMode, stepModuleTreeSelectionDisabled]);
  const explorerPickableFaces = useMemo(
    () => explorerPickableReferences.filter((reference) => isFaceReference(reference)),
    [isFaceReference, explorerPickableReferences]
  );
  const explorerPickableEdges = useMemo(
    () => explorerPickableReferences.filter((reference) => isEdgeReference(reference)),
    [isEdgeReference, explorerPickableReferences]
  );
  const explorerPickableVertices = EMPTY_LIST;
  const referenceSelectionStatus = isAssemblyView && isInspectingAssemblyPart
    ? inspectedAssemblyReferenceStatus
    : referenceStatus;
  const hasExplorerPickableTopology = Boolean(
    explorerPickableFaces.length ||
    explorerPickableEdges.length ||
    explorerPickableVertices.length
  );
  const topologySelectionActive = (isAssemblyView && isInspectingAssemblyPart) || topLevelReferenceSelectionActive;
  const referenceSelectionUnavailable = stepModuleTreeSelectionDisabled || (
    effectiveRenderFormat === RENDER_FORMAT.STEP &&
    selectedEntryHasReferences &&
    topologySelectionActive &&
    !explorerInAssemblyMode &&
    (
      referenceSelectionStatus === REFERENCE_STATUS.DISABLED ||
      referenceSelectionStatus === REFERENCE_STATUS.ERROR ||
      (
        referenceSelectionStatus === REFERENCE_STATUS.READY &&
        !!effectiveSelectorRuntime &&
        !hasExplorerPickableTopology
      )
    )
  );
  const referenceSelectionPending = (
    effectiveRenderFormat === RENDER_FORMAT.STEP &&
    selectedEntryHasReferences &&
    topologySelectionActive &&
    !explorerInAssemblyMode &&
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

    if (effectiveRenderFormat === RENDER_FORMAT.DXF && dxfExplorerLoading) {
      return {
        loading: true,
        label: selectedEntryHasDxf ? (dxfLoadStage || "loading DXF") : "building",
        title: explorerLoadingLabel
      };
    }

    if (isRobotRenderFormat(effectiveRenderFormat) && urdfExplorerLoading) {
      return {
        loading: true,
        label: selectedEntryHasUrdf ? (urdfLoadStage || (effectiveRenderFormat === RENDER_FORMAT.SDF ? "loading SDF" : "loading URDF")) : "building",
        title: explorerLoadingLabel
      };
    }

    if (effectiveRenderFormat === RENDER_FORMAT.STEP && stepUpdateInProgress) {
      return {
        loading: true,
        label: "building",
        title: explorerLoadingLabel
      };
    }

    if ([RENDER_FORMAT.STEP, RENDER_FORMAT.STL, RENDER_FORMAT.THREE_MF, RENDER_FORMAT.GLB].includes(effectiveRenderFormat) && stepExplorerLoading) {
      const activeMeshLoadStage = meshLoadTargetFile === fileKey(selectedEntry)
        ? meshLoadStage
        : "";
      return {
        loading: true,
        label: selectedEntryHasMesh ? (activeMeshLoadStage || "loading mesh") : "building",
        title: explorerLoadingLabel
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
    dxfExplorerLoading,
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
    stepUpdateInProgress,
    stepExplorerLoading,
    urdfLoadStage,
    urdfExplorerLoading,
    explorerLoadingLabel
  ]);
  const explorerSelectedPartIds = useMemo(() => {
    if (isStepView) {
      return [];
    }
    return uniqueStringList(
      selectedPartIds.flatMap((id) => renderPartIdsForAssemblySelection(
        id,
        selectedRenderPartIdByAssemblyPartId[String(id || "").trim()]
      ))
    );
  }, [
    isStepView,
    renderPartIdsForAssemblySelection,
    selectedPartIds,
    selectedRenderPartIdByAssemblyPartId
  ]);
  const explorerHoveredPartIds = useMemo(() => {
    if (!isAssemblyView || isInspectingAssemblyPart || !hoveredPartId) {
      return hoveredPartId;
    }
    const normalizedHoveredPartId = String(hoveredPartId || "").trim();
    const hoveredSelectionId = resolvePickedAssemblyPartId(normalizedHoveredPartId);
    const highlightedPartIds = renderPartIdsForAssemblySelection(hoveredSelectionId, normalizedHoveredPartId);
    return highlightedPartIds.length ? highlightedPartIds : hoveredPartId;
  }, [
    hoveredPartId,
    isAssemblyView,
    isInspectingAssemblyPart,
    renderPartIdsForAssemblySelection,
    resolvePickedAssemblyPartId
  ]);
  const explorerFocusedPartIds = useMemo(() => {
    if (!isStepView || !selectedPartIds.length) {
      return [];
    }
    return uniqueStringList(
      selectedPartIds.flatMap((id) => renderPartIdsForAssemblySelection(
        id,
        selectedRenderPartIdByAssemblyPartId[String(id || "").trim()]
      ))
    );
  }, [
    isStepView,
    renderPartIdsForAssemblySelection,
    selectedPartIds,
    selectedRenderPartIdByAssemblyPartId
  ]);
  const explorerHiddenPartIds = useMemo(() => {
    return hiddenPartIds;
  }, [hiddenPartIds]);
  const explorerAssemblyRenderParts = useMemo(() => {
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
    explorerRef.current?.setPerspective?.(restoredPerspective, { animate: true });
    activePerspectiveRef.current = restoredPerspective;
    setExplorerPerspective(restoredPerspective);
    return true;
  }, []);
  const handleBeginUrdfPosePicker = useCallback(() => {
    if (!selectedUrdfFileRef || !selectedUrdfMoveIt2ActionsEnabled) {
      return;
    }
    const originalPerspective = clonePerspectiveSnapshot(explorerRef.current?.getPerspective?.() || activePerspectiveRef.current);
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
      .map((id) => effectiveActiveReferenceMap.get(id))
      .filter(Boolean);
    if (!isAssemblyView && selectedPartIds.includes(STEP_MODEL_ROOT_ID)) {
      const wholeStepEntryReference = buildWholeStepEntryCopyReference(selectedEntry);
      if (wholeStepEntryReference) {
        selectedReferencesForCopy.push(wholeStepEntryReference);
      }
    }
    const selectedPartsForCopy = supportsPartSelection && isAssemblyView
      ? selectedPartIds.map((id) => assemblyPartMap.get(id)).filter(Boolean)
      : [];

    return buildSelectionCopyPayload({
      references: selectedReferencesForCopy,
      parts: selectedPartsForCopy,
      entry: selectedEntry
    });
  }, [
    assemblyPartMap,
    effectiveActiveReferenceMap,
    isAssemblyView,
    selectedEntry,
    selectedPartIds,
    selectedReferenceIds,
    supportsPartSelection
  ]);
  const copyButtonLabel = useMemo(
    () => buildSelectionCopyButtonLabel(copySelectionPayload.lines, { count: copySelectionPayload.copiedCount }),
    [copySelectionPayload.copiedCount, copySelectionPayload.lines]
  );

  useEffect(() => {
    if (!pendingCadRefQueryParams.length) {
      return;
    }

    if (!selectedEntry) {
      if (!cadRefQueryHasKnownEntry(pendingCadRefQueryParams, catalogEntries)) {
        setPendingCadRefQueryParams([]);
      }
      return;
    }

    const selectionRequest = collectCadRefSelectionRequest(pendingCadRefQueryParams, selectedEntry);
    if (!selectionRequest.hasMatchingToken) {
      if (!cadRefQueryHasKnownEntry(pendingCadRefQueryParams, catalogEntries)) {
        setPendingCadRefQueryParams([]);
      }
      return;
    }

    if (selectionRequest.needsParts && !assemblyPartsLoaded) {
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
    setSelectedRenderPartIdByAssemblyPartId({});
    setSelectedWholeEntryCadRefToken(
      resolvedSelection.hasWholeEntryToken
        ? buildCadRefToken({ cadPath: cadPathForEntry(selectedEntry) })
        : ""
    );
    setExpandedAssemblyPartIds((current) => (
      orderedStringListEqual(current, resolvedSelection.expandedAssemblyPartIds)
        ? current
        : resolvedSelection.expandedAssemblyPartIds
    ));
    const resolvedTreeNodeIds = uniqueStringList([
      ...resolvedSelection.selectedPartIds.flatMap((id) => collectStepTreeAncestorIds(stepTreeRoot, id)),
      ...resolvedSelection.expandedAssemblyPartIds.flatMap((id) => collectStepTreeAncestorIds(stepTreeRoot, id)),
      ...resolvedSelection.expandedAssemblyPartIds
    ]);
    if (resolvedTreeNodeIds.length) {
      setExpandedStepTreeNodeIds((current) => uniqueStringList([...current, ...resolvedTreeNodeIds]));
    }
    setHoveredListReferenceId("");
    setHoveredModelReferenceId("");
    setHoveredListPartId("");
    setHoveredModelPartId("");
    setCopyStatus("");
    setTabToolMode(TAB_TOOL_MODE.REFERENCES);
    setPendingCadRefQueryParams([]);
  }, [
    assemblyPartsLoaded,
    assemblyNodes,
    catalogEntries,
    isAssemblyView,
    pendingCadRefQueryParams,
    selectedEntry,
    selectedEntryHasReferences,
    selectedReferencesMatch,
    selectedReferenceIdsRef,
    selectedPartIdsRef,
    stepTreeRoot,
    visibleReferences
  ]);

  useEffect(() => {
    if (!cadWorkspaceSessionBootstrappedRef.current || pendingCadRefQueryParams.length) {
      return;
    }
    writeCadRefQueryParams(selectedEntry ? [
      ...(selectedWholeEntryCadRefToken ? [selectedWholeEntryCadRefToken] : []),
      ...copySelectionPayload.lines
    ] : []);
  }, [
    copySelectionPayload.lines,
    pendingCadRefQueryParams,
    selectedEntry,
    selectedWholeEntryCadRefToken,
    cadWorkspaceSessionBootstrappedRef
  ]);

  const toggleReferenceSelection = useCallback((referenceId, { multiSelect = false } = {}) => {
    if (stepUpdateInProgress || stepModuleTreeSelectionDisabled) {
      return;
    }
    const next = computeNextSelectionIds(selectedReferenceIdsRef.current, referenceId, { multiSelect });
    if (next.length && !isDesktop) {
      setSidebarOpen(false);
    }
    setSelectedWholeEntryCadRefToken("");
    selectedReferenceIdsRef.current = next;
    setSelectedReferenceIds(next);
  }, [isDesktop, stepModuleTreeSelectionDisabled, stepUpdateInProgress]);

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
    if (stepUpdateInProgress) {
      setCopyStatus("STEP update in progress. Please wait.");
      return;
    }
    const selectedReferencesForCopy = selectedReferenceIdsRef.current
      .map((id) => effectiveActiveReferenceMap.get(id))
      .filter(Boolean);
    if (!isAssemblyView && selectedPartIdsRef.current.includes(STEP_MODEL_ROOT_ID)) {
      const wholeStepEntryReference = buildWholeStepEntryCopyReference(selectedEntry);
      if (wholeStepEntryReference) {
        selectedReferencesForCopy.push(wholeStepEntryReference);
      }
    }
    const selectedPartsForCopy = supportsPartSelection && isAssemblyView
      ? selectedPartIdsRef.current.map((id) => assemblyPartMap.get(id)).filter(Boolean)
      : [];
    if (!selectedReferencesForCopy.length && !selectedPartsForCopy.length) {
      setCopyStatus("Nothing selected");
      return;
    }

    const { lines, missingPartNames } = buildSelectionCopyPayload({
      references: selectedReferencesForCopy,
      parts: selectedPartsForCopy,
      entry: selectedEntry
    });
    if (!lines.length) {
      setCopyStatus(
        missingPartNames.length === 1
          ? `No CAD reference is available for ${missingPartNames[0]}`
          : "No CAD references are available for the selection"
      );
      return;
    }

    try {
      await copyTextToClipboard(lines.join("\n"));
      const copiedCount = selectedReferencesForCopy.length + selectedPartsForCopy.length - missingPartNames.length;
      const missingSuffix = missingPartNames.length
        ? ` (${missingPartNames.length} unavailable)`
        : "";
      setCopyStatus(`Copied ${copiedCount} ref${copiedCount === 1 ? "" : "s"}${missingSuffix}`);
    } catch (err) {
      setCopyStatus(err instanceof Error ? err.message : "Clipboard write failed");
    }
  }, [
    assemblyPartMap,
    effectiveActiveReferenceMap,
    isAssemblyView,
    selectedEntry,
    setScreenshotStatus,
    supportsPartSelection,
    stepUpdateInProgress
  ]);

  const handleCopyViewState = useCallback(async () => {
    if (!selectedEntry) {
      setCopyStatus("No file selected");
      return;
    }

    try {
      const selectedReferencesForCopy = selectedReferenceIdsRef.current
        .map((id) => effectiveActiveReferenceMap.get(id))
        .filter(Boolean);
      if (!isAssemblyView && selectedPartIdsRef.current.includes(STEP_MODEL_ROOT_ID)) {
        const wholeStepEntryReference = buildWholeStepEntryCopyReference(selectedEntry);
        if (wholeStepEntryReference) {
          selectedReferencesForCopy.push(wholeStepEntryReference);
        }
      }
      const selectedPartsForCopy = supportsPartSelection && isAssemblyView
        ? selectedPartIdsRef.current.map((id) => assemblyPartMap.get(id)).filter(Boolean)
        : [];
      const selectedCadRefs = buildSelectionCopyPayload({
        references: selectedReferencesForCopy,
        parts: selectedPartsForCopy,
        entry: selectedEntry
      }).lines;
      const currentPerspective = clonePerspectiveSnapshot(
        explorerRef.current?.getPerspective?.() ||
        activePerspectiveRef.current ||
        explorerPerspective
      );
      const state = buildCadViewState({
        entry: selectedEntry,
        cadPath: cadPathForEntry(selectedEntry),
        renderFormat: effectiveRenderFormat,
        perspective: currentPerspective,
        selectedPartIds: selectedPartIdsRef.current,
        selectedParts: selectedPartsForCopy,
        selectedReferenceIds: selectedReferenceIdsRef.current,
        selectedReferences: selectedReferencesForCopy,
        selectedCadRefs,
        hoveredPartId,
        hoveredReferenceId,
        hiddenPartIds,
        expandedTreeNodeIds: expandedStepTreeNodeIds,
        expandedAssemblyPartIds,
        clipSettings: isStepView ? stepClipSettings : null,
        themeSettings,
        layout: {
          sidebarOpen,
          selectedFileSheetKind,
          tabToolsOpen,
          workspaceLayoutMode
        },
        url: typeof window !== "undefined" ? window.location.href : "",
        notes: "Paste this payload into an issue, chat, or local repro script to restore the reviewed CAD context."
      });
      await copyTextToClipboard(formatCadViewStateForClipboard(state));
      setScreenshotStatus("");
      setCopyStatus("Copied view state");
    } catch (error) {
      setScreenshotStatus("");
      setCopyStatus(error instanceof Error ? error.message : "Clipboard write failed");
    }
  }, [
    assemblyPartMap,
    effectiveActiveReferenceMap,
    effectiveRenderFormat,
    expandedAssemblyPartIds,
    expandedStepTreeNodeIds,
    explorerPerspective,
    hiddenPartIds,
    hoveredPartId,
    hoveredReferenceId,
    isAssemblyView,
    isStepView,
    selectedEntry,
    selectedFileSheetKind,
    sidebarOpen,
    stepClipSettings,
    supportsPartSelection,
    tabToolsOpen,
    themeSettings,
    workspaceLayoutMode
  ]);

  const expandStepTreeAroundNode = useCallback((nodeId, { expandSelf = false } = {}) => {
    const normalizedNodeId = String(nodeId || "").trim();
    if (!normalizedNodeId || !stepTreeRoot) {
      return;
    }
    const node = assemblyPartMap.get(normalizedNodeId);
    const ancestorIds = collectStepTreeAncestorIds(stepTreeRoot, normalizedNodeId);
    const selfIds = expandSelf && stepTreeNodeChildren(node).length ? [normalizedNodeId] : [];
    const idsToExpand = [...ancestorIds, ...selfIds].filter(Boolean);
    if (!idsToExpand.length) {
      return;
    }
    setExpandedStepTreeNodeIds((current) => uniqueStringList([...current, ...idsToExpand]));
  }, [assemblyPartMap, stepTreeRoot]);

  const syncPrimaryStepSelection = useCallback((selectedIds) => {
    const primaryId = String(selectedIds[selectedIds.length - 1] || "").trim();
    if (!isAssemblyView || !primaryId || primaryId === "root" || primaryId === STEP_MODEL_ROOT_ID) {
      setExpandedAssemblyPartIds([]);
      return;
    }
    setExpandedAssemblyPartIds([primaryId]);
    expandStepTreeAroundNode(primaryId);
  }, [expandStepTreeAroundNode, isAssemblyView]);

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

  const togglePartSelection = useCallback((partId, { multiSelect = false, renderPartId = "" } = {}) => {
    if (stepUpdateInProgress || stepModuleTreeSelectionDisabled) {
      return;
    }
    const normalizedPartId = String(partId || "").trim();
    const next = computeNextSelectionIds(selectedPartIdsRef.current, partId, { multiSelect });
    if (next.length && !isDesktop) {
      setSidebarOpen(false);
    }
    setSelectedWholeEntryCadRefToken("");
    selectedPartIdsRef.current = next;
    setSelectedPartIds(next);
    syncPrimaryStepSelection(next);
    expandStepTreeAroundNode(normalizedPartId, { expandSelf: true });
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
  }, [
    expandStepTreeAroundNode,
    isDesktop,
    renderPartIdForAssemblySelection,
    stepModuleTreeSelectionDisabled,
    stepUpdateInProgress,
    syncPrimaryStepSelection
  ]);

  const selectStepTreeNode = useCallback((nodeId, { multiSelect = false } = {}) => {
    togglePartSelection(nodeId, { multiSelect });
  }, [togglePartSelection]);

  const clearAssemblySelection = useCallback(() => {
    selectedPartIdsRef.current = [];
    selectedReferenceIdsRef.current = [];
    setSelectedWholeEntryCadRefToken("");
    setSelectedPartIds([]);
    setSelectedRenderPartIdByAssemblyPartId({});
    setExpandedAssemblyPartIds([]);
    setSelectedReferenceIds([]);
    setHoveredListPartId("");
    setHoveredModelPartId("");
    setHoveredListReferenceId("");
    setHoveredModelReferenceId("");
    setCopyStatus("");
  }, []);

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

  const togglePartVisibility = useCallback((partId) => {
    const leafIds = renderPartIdsForAssemblySelection(partId);
    if (!leafIds.length) {
      return;
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
  }, [renderPartIdsForAssemblySelection]);

  const handleHideSelectedParts = useCallback(() => {
    const nextSelectedPartIds = [...new Set(
      selectedPartIdsRef.current
        .map((partId) => String(partId || "").trim())
        .filter(Boolean)
    )];
    if (nextSelectedPartIds.length < 2) {
      return;
    }
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
  }, [renderPartIdsForAssemblySelection]);

  const handleShowAllHiddenParts = useCallback(() => {
    setHiddenPartIds((current) => (current.length ? [] : current));
  }, []);

  const handleModelHoverChange = useCallback((referenceId) => {
    if (stepModuleTreeSelectionDisabled) {
      setHoveredModelReferenceId("");
      setHoveredModelPartId("");
      return;
    }
    if (explorerInAssemblyMode) {
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
  }, [explorerInAssemblyMode, resolvePickedAssemblyPartId, stepModuleTreeSelectionDisabled]);

  const handleModelReferenceActivate = useCallback((referenceId, { multiSelect = false } = {}) => {
    if (stepUpdateInProgress || stepModuleTreeSelectionDisabled) {
      return;
    }
    if (explorerInAssemblyMode) {
      const pickedPartId = String(referenceId || "").trim();
      const nextPartId = resolvePickedAssemblyPartId(pickedPartId);
      if (!nextPartId) {
        clearAssemblySelection();
        return;
      }
      togglePartSelection(nextPartId, { multiSelect, renderPartId: pickedPartId });
      return;
    }
    const nextReferenceId = String(referenceId || "").trim();
    if (!nextReferenceId) {
      if (isStepView && selectedPartIdsRef.current.length) {
        clearAssemblySelection();
        return;
      }
      clearReferenceSelection();
      return;
    }
    if (!effectiveActiveReferenceMap.has(nextReferenceId)) {
      return;
    }
    toggleReferenceSelection(nextReferenceId, { multiSelect });
  }, [
    clearAssemblySelection,
    clearReferenceSelection,
    effectiveActiveReferenceMap,
    resolvePickedAssemblyPartId,
    stepUpdateInProgress,
    toggleReferenceSelection,
    togglePartSelection,
    explorerInAssemblyMode,
    isStepView,
    stepModuleTreeSelectionDisabled
  ]);

  const handleModelReferenceDoubleActivate = useCallback(() => {}, []);

  const handleSelectEntry = useCallback((key) => {
    activateEntryTab(key);
    if (!isDesktop) {
      setSidebarOpen(false);
    }
  }, [activateEntryTab, isDesktop]);

  const handleSelectTabToolMode = useCallback((mode) => {
    setExplorerAlertOpen(false);
    const normalizedMode = mode === TAB_TOOL_MODE.DRAW ? TAB_TOOL_MODE.DRAW : TAB_TOOL_MODE.REFERENCES;
    setTabToolMode(normalizedMode);
    if (normalizedMode === TAB_TOOL_MODE.DRAW && drawingTool === DRAWING_TOOL.SURFACE_LINE) {
      setDrawingTool(DRAWING_TOOL.FREEHAND);
    }
  }, [drawingTool]);

  const handleToggleFileSheet = useCallback(() => {
    if (!selectedFileSheetKind) {
      return;
    }
    setThemeMenuOpen(false);
    setExplorerAlertOpen(false);
    setTabToolsOpen((current) => {
      const nextOpen = !current;
      if (nextOpen && !isDesktop) {
        setSidebarOpen(false);
      }
      return nextOpen;
    });
  }, [isDesktop, selectedFileSheetKind, setThemeMenuOpen, setTabToolsOpen]);

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
  }, []);

  useCadWorkspaceShortcuts({
    copyStatus,
    screenshotStatus,
    setCopyStatus,
    setScreenshotStatus,
    previewMode,
    explorerAlertOpen,
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
    setExplorerAlertOpen,
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
      if (!explorerRef.current?.captureScreenshot) {
        throw new Error("Explorer not ready");
      }
      await explorerRef.current.captureScreenshot({ filename, mode: "download" });
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
      if (!explorerRef.current?.captureScreenshot) {
        throw new Error("Explorer not ready");
      }
      await explorerRef.current.captureScreenshot({ filename, mode: "clipboard" });
      setCopyStatus("");
      setScreenshotStatus("Copied screenshot to clipboard");
    } catch (captureError) {
      setCopyStatus("");
      setScreenshotStatus(captureError instanceof Error ? captureError.message : "Clipboard copy failed");
    }
  }, [selectedEntry]);

  const handleEnterPreviewMode = useCallback(() => {
    if (effectiveRenderFormat === RENDER_FORMAT.DXF || explorerLoading || !selectedMeshData || previewMode) {
      return;
    }
    previewUiStateRef.current = {
      sidebarOpen,
      tabToolsOpen,
      tabToolMode,
      themeMenuOpen: false,
      explorerAlertOpen
    };
    setCopyStatus("");
    setScreenshotStatus("");
    setDrawingStrokes([]);
    setDrawingUndoStack([]);
    setDrawingRedoStack([]);
    setExplorerAlertOpen(false);
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
    selectedMeshData,
    tabToolMode,
    tabToolsOpen,
    explorerAlertOpen,
    explorerLoading
  ]);

  const toggleDirectory = (directoryId) => {
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
  const themeSections = (
    <ThemeSettingsSections
      themeSettings={themeSettings}
      updateThemeSettings={updateThemeSettings}
    />
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
          explorerRef={explorerRef}
          renderFormat={effectiveRenderFormat}
          renderPartsIndividually={isUrdfView || Boolean(selectedStepModuleRuntime)}
          parameters={selectedStepModuleRuntime}
          selectedMeshData={selectedMeshData}
          selectedDxfData={selectedDxfData}
          selectedDxfMeshData={selectedDxfMeshData}
          selectedKey={selectedKey}
          selectedDxfKey={selectedDxfPreviewKey}
          missingFileRef={missingFileRef}
          explorerPerspective={explorerPerspective}
          explorerPerspectiveRef={activePerspectiveRef}
          themeSettings={themeSettings}
          previewMode={previewMode}
          viewportFrameInsets={viewportFrameInsets}
          explorerLoading={explorerLoading}
          explorerAlert={explorerAlert}
          stepUpdateInProgress={effectiveRenderFormat === RENDER_FORMAT.STEP && stepUpdateInProgress}
          referenceSelectionPending={referenceSelectionPending}
          referenceSelectionUnavailable={referenceSelectionUnavailable}
          viewPlaneOffsetRight={viewportFrameInsets.right + 16}
          explorerMode={explorerMode}
          assemblyParts={explorerAssemblyRenderParts}
          hiddenPartIds={explorerHiddenPartIds}
          selectedPartIds={explorerSelectedPartIds}
          hoveredPartId={explorerHoveredPartIds}
          hoveredReferenceId={hoveredReferenceId}
          selectedReferenceIds={selectedReferenceIds}
          selectorRuntime={effectiveSelectorRuntime}
          pickableFaces={explorerPickableFaces}
          pickableEdges={explorerPickableEdges}
          pickableVertices={explorerPickableVertices}
          focusedPartIds={explorerFocusedPartIds}
          clip={isStepView ? stepClipSettings : null}
          drawToolActive={drawToolActive}
          drawingTool={drawingTool}
          drawingStrokes={drawingStrokes}
          handleDrawingStrokesChange={handleDrawingStrokesChange}
          handlePerspectiveChange={handlePerspectiveChange}
          handleModelHoverChange={handleModelHoverChange}
          handleModelReferenceActivate={handleModelReferenceActivate}
          handleModelReferenceDoubleActivate={handleModelReferenceDoubleActivate}
          handleExplorerAlertChange={handleExplorerAlertChange}
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

      <FileExplorerSidebar
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
        resizable={isDesktop}
        onStartResize={handleStartSidebarResize}
      />

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
          themePresets={availableThemePresets}
          themeSettings={themeSettings}
          themePresetId={themePresetId}
          updateThemeSettings={updateThemeSettings}
          handleResetThemeSettings={handleResetThemeSettings}
          handleSaveCustomThemePreset={handleSaveCustomThemePreset}
          handleDeleteCustomThemePreset={handleDeleteCustomThemePreset}
          filenameLoadActivity={filenameLoadActivity}
          fileSheetKind={selectedFileSheetKind}
          fileSheetOpen={fileSheetOpen}
          onToggleFileSheet={handleToggleFileSheet}
        />

        <div className="pointer-events-none relative min-h-0 flex-1 overflow-hidden">
          <div className="flex h-full min-w-0">
            <div className="pointer-events-none relative min-w-0 flex-1 overflow-hidden">
              <FloatingToolBar
                previewMode={previewMode}
                selectedEntry={selectedEntry}
                renderFormat={effectiveRenderFormat}
                floatingCadToolbarPosition={floatingCadToolbarPosition}
                selectionToolActive={selectionToolActive}
                referenceSelectionPending={referenceSelectionPending}
                referenceSelectionUnavailable={referenceSelectionUnavailable}
                urdfPosePickerAvailable={selectedUrdfMoveIt2ActionsEnabled}
                urdfPosePickerActive={urdfPosePickerActive}
                handleToggleUrdfPosePicker={handleToggleUrdfPosePicker}
                drawToolActive={drawToolActive}
                handleSelectTabToolMode={handleSelectTabToolMode}
                explorerLoading={explorerLoading}
                selectedMeshData={selectedMeshData}
                selectedDxfData={selectedDxfData}
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
                handleCopyViewState={handleCopyViewState}
                handleScreenshotCopy={handleScreenshotCopy}
                handleScreenshotDownload={handleScreenshotDownload}
              />

              <ExplorerLoadingOverlay
                explorerLoading={explorerLoading}
                previewMode={previewMode}
              />
            </div>

            {selectedFileSheetKind === "dxf" ? (
              <DxfFileSheet
                key={`dxf:${selectedKey}`}
                open={fileSheetOpen}
                isDesktop={isDesktop}
                width={activeSheetWidth || tabToolsWidth}
                onStartResize={handleStartFileSheetResize}
                valueMm={effectiveDxfThicknessMm}
                bendLines={selectedDxfBendLines}
                bendSettings={normalizedSelectedDxfBendSettings}
                hasDxfData={!!selectedDxfData}
                explorerLoading={explorerLoading}
                onThicknessChange={setDxfThicknessMm}
                onBendChange={handleDxfBendSettingChange}
                themeSections={themeSections}
              />
            ) : null}

            {selectedFileSheetKind === "step" ? (
              <StepFileSheet
                key={`step:${selectedKey}`}
                open={fileSheetOpen}
                isDesktop={isDesktop}
                width={activeSheetWidth || tabToolsWidth}
                onStartResize={handleStartFileSheetResize}
                selectedEntry={selectedEntry}
                explorerLoading={explorerLoading || assemblySidebarLoading}
                isAssemblyView={isAssemblyView}
                stepTreeRoot={stepTreeRoot}
                expandedTreeNodeIds={expandedStepTreeNodeIds}
                selectedPartIds={selectedPartIds}
                hoveredPartId={hoveredPartId}
                hiddenPartIds={hiddenPartIds}
                onSelectTreeNode={selectStepTreeNode}
                onToggleTreeNode={toggleStepTreeNode}
                onClearSelection={clearAssemblySelection}
                onHoverTreeNode={setHoveredListPartId}
                treeSelectionDisabled={stepModuleTreeSelectionDisabled}
                treeSelectionDisabledReason={stepModuleTreeSelectionDisabledReason}
                onTogglePartVisibility={togglePartVisibility}
                hideSelectedParts={handleHideSelectedParts}
                showAllHiddenParts={handleShowAllHiddenParts}
                clipSettings={stepClipSettings}
                onClipSettingsChange={setStepClipSettings}
                clipBounds={selectedMeshData?.bounds || null}
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
                  onEnabledChange: handleStepModuleEnabledChange
                }}
                themeSections={themeSections}
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
                themeSections={themeSections}
              />
            ) : null}

            {selectedFileSheetKind === "mesh" ? (
              <MeshFileSheet
                key={`mesh:${selectedKey}`}
                open={fileSheetOpen}
                title={selectedEntrySourceFormat === RENDER_FORMAT.THREE_MF ? "3MF" : selectedEntrySourceFormat === RENDER_FORMAT.GLB ? "GLB" : "STL"}
                isDesktop={isDesktop}
                width={activeSheetWidth || tabToolsWidth}
                onStartResize={handleStartFileSheetResize}
                themeSections={themeSections}
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

        <ExplorerAlertDialog
          explorerAlertOpen={explorerAlertOpen}
          explorerAlert={explorerAlert}
          previewMode={previewMode}
          setExplorerAlertOpen={setExplorerAlertOpen}
        />
      </SidebarInset>
    </SidebarProvider>
  );
}

"use client";

import { startTransition, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeftRight, ArrowRight, Circle, Eraser, Minus, PaintBucket, PenTool, Square } from "lucide-react";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import CadRenderPane from "./workbench/CadRenderPane";
import DxfFileSheet from "./workbench/DxfFileSheet";
import FileExplorerSidebar from "./workbench/FileExplorerSidebar";
import LookSettingsPopover from "./workbench/LookSettingsPopover";
import StepAssemblyFileSheet from "./workbench/StepAssemblyFileSheet";
import StatusToast from "./workbench/StatusToast";
import UrdfFileSheet from "./workbench/UrdfFileSheet";
import ViewerAlertDialog from "./workbench/ViewerAlertDialog";
import ViewerLoadingOverlay from "./workbench/ViewerLoadingOverlay";
import CadWorkspaceAssemblyInspectPill from "./workbench/CadWorkspaceAssemblyInspectPill";
import FloatingToolBar from "./workbench/FloatingToolBar";
import CadWorkspaceTopBar from "./workbench/CadWorkspaceTopBar";
import MeasureFileSheet from "./workbench/MeasureFileSheet";
import { useCadAssets } from "./workbench/hooks/useCadAssets";
import { useCadWorkspaceLayout } from "./workbench/hooks/useCadWorkspaceLayout";
import { useCadWorkspaceSelection } from "./workbench/hooks/useCadWorkspaceSelection";
import { useCadWorkspaceSession } from "./workbench/hooks/useCadWorkspaceSession";
import { useCadWorkspaceSelectors } from "./workbench/hooks/useCadWorkspaceSelectors";
import { useCadWorkspaceShortcuts } from "./workbench/hooks/useCadWorkspaceShortcuts";
import {
  applyThemeToDocument,
  DARK_THEME_ID
} from "../lib/themes";
import {
  cloneLookSettings,
  DEFAULT_LOOK_SETTINGS,
  normalizeLookSettings
} from "../lib/lookSettings";
import { clonePerspectiveSnapshot } from "../lib/perspective";
import {
  ASSET_STATUS,
  DRAWING_TOOL,
  RENDER_FORMAT,
  REFERENCE_STATUS,
  TAB_TOOL_MODE
} from "../lib/workbench/constants";
import {
  buildCadWorkspaceSessionState,
  cloneDrawingStrokes,
  cloneTabSnapshot,
  createTabRecord,
  dxfBendSettingsEqual,
  drawingStrokesEqual,
  LOOK_SETTINGS_STORAGE_KEY,
  CAD_WORKSPACE_DEFAULT_GLASS_TONE,
  normalizeCadWorkspaceGlassTone,
  readDxfBendOverridesForEntry,
  readLookSettings,
  readCadWorkspaceGlassTone,
  readCadWorkspaceSessionState,
  writeDxfBendOverridesForEntry,
  writeLookSettings,
  writeThemePreference,
  writeCadWorkspaceGlassTone,
  tabSnapshotEqual,
  CAD_WORKSPACE_DEFAULT_SIDEBAR_WIDTH,
  CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH,
  writeCadWorkspaceSessionState
} from "../lib/workbench/persistence";
import {
  buildSidebarDirectoryTree,
  cadPathForEntry,
  collectAncestorDirectoryIds,
  collectSidebarDirectoryIds,
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
  buildDefaultUrdfJointValues,
  buildUrdfMeshGeometry,
  clampJointValueDeg,
  poseUrdfMeshData
} from "../lib/urdf/kinematics";
import {
  advanceUrdfJointValues,
  jointValueMapsClose,
  URDF_JOINT_ANIMATION_FOLLOW_MS
} from "../lib/urdf/jointAnimation";
import { buildSelectorRuntime } from "../lib/selectors/runtime";
import { formatMeasurementValue, measurementForReferences } from "../lib/measurements/measureTopology";
import {
  assemblyBreadcrumb,
  buildAssemblyLeafToNodePickMap,
  descendantLeafPartIds,
  findAssemblyNode,
  flattenAssemblyNodes,
  flattenAssemblyLeafParts,
  leafPartIdsForAssemblySelection
} from "../lib/assembly/meshData";
import { copyTextToClipboard } from "../lib/clipboard";

const DEFAULT_DOCUMENT_TITLE = "CAD Explorer";
const EMPTY_LIST = Object.freeze([]);
const CAD_BUILD_COMMANDS = {
  dxf: "python skills/cad/scripts/gen_dxf",
  stepAssembly: "python skills/cad/scripts/gen_step_assembly",
  stepPart: "python skills/cad/scripts/gen_step_part",
  urdf: "python skills/urdf/scripts/gen_urdf"
};
const DEFAULT_URDF_ANIMATION_SETTINGS = Object.freeze({
  introEnabled: true,
  speed: 1
});
const MIN_URDF_ANIMATION_SPEED = 0.25;
const MAX_URDF_ANIMATION_SPEED = 2.5;
const DESKTOP_SIDEBAR_MIN_WIDTH = 150;
const DESKTOP_SIDEBAR_MAX_WIDTH = 520;
const DEFAULT_SIDEBAR_WIDTH = CAD_WORKSPACE_DEFAULT_SIDEBAR_WIDTH;
const DESKTOP_TAB_TOOLS_MIN_WIDTH = 160;
const DESKTOP_TAB_TOOLS_MAX_WIDTH = 560;
const DEFAULT_TAB_TOOLS_WIDTH = CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH;
const CAD_WORKSPACE_TOP_BAR_HEIGHT = 44;
const CAD_WORKSPACE_SESSION_PERSIST_DELAY_MS = 120;
const MOBILE_FILE_EXPLORER_MEDIA_QUERY = "(max-width: 767px)";
const DEFAULT_MEASURE_DENSITY_G_CM3 = "1.24";

function clampPanelWidth(value, minWidth, maxWidth) {
  return Math.min(Math.max(value, minWidth), Math.max(minWidth, maxWidth));
}

function toFiniteNumber(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function animationNowMs() {
  if (typeof performance !== "undefined" && typeof performance.now === "function") {
    return performance.now();
  }
  return Date.now();
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

function roundedUrdfJointValue(value) {
  const numericValue = toFiniteNumber(value, 0);
  const rounded = Math.round(numericValue * 1000) / 1000;
  return Object.is(rounded, -0) ? 0 : rounded;
}

function normalizeUrdfIntroAnimationEnabled(value) {
  return value === true;
}

function normalizeUrdfAnimationSpeed(value, fallback = DEFAULT_URDF_ANIMATION_SETTINGS.speed) {
  const numericValue = toFiniteNumber(value, fallback);
  return Math.min(Math.max(numericValue, MIN_URDF_ANIMATION_SPEED), MAX_URDF_ANIMATION_SPEED);
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

function buildUrdfLinkIntroOrderMap(urdfData) {
  const orderByLink = new Map();
  const rootLink = String(urdfData?.rootLink || "").trim();
  if (rootLink) {
    orderByLink.set(rootLink, 0);
  }
  const joints = Array.isArray(urdfData?.joints) ? urdfData.joints : [];
  joints.forEach((joint, index) => {
    const parentLink = String(joint?.parentLink || "").trim();
    const childLink = String(joint?.childLink || "").trim();
    if (!childLink) {
      return;
    }
    const parentOrder = orderByLink.get(parentLink);
    const introOrder = Number.isFinite(parentOrder) ? parentOrder + 1 : index + 1;
    orderByLink.set(childLink, introOrder);
  });
  return orderByLink;
}

function buildUrdfWrappedJointNameSet(urdfData) {
  return new Set(
    (Array.isArray(urdfData?.joints) ? urdfData.joints : [])
      .filter((joint) => String(joint?.type || "").trim().toLowerCase() === "continuous")
      .map((joint) => String(joint?.name || "").trim())
      .filter(Boolean)
  );
}

function useAnimatedUrdfJointValues(
  targetValues,
  animationKey,
  animationSettings = DEFAULT_URDF_ANIMATION_SETTINGS,
  wrappedJointNames = null
) {
  const initialAnimationKey = String(animationKey || "");
  const [displayValues, setDisplayValues] = useState(() => cloneJointValueMap(targetValues));
  const displayValuesRef = useRef(displayValues);
  const targetValuesRef = useRef(cloneJointValueMap(targetValues));
  const animationRef = useRef({
    frameId: 0,
    key: initialAnimationKey,
    lastTimestamp: 0
  });

  useEffect(() => {
    displayValuesRef.current = displayValues;
  }, [displayValues]);

  const animationSpeed = normalizeUrdfAnimationSpeed(animationSettings?.speed);

  const cancelAnimation = () => {
    if (animationRef.current.frameId && typeof cancelAnimationFrame === "function") {
      cancelAnimationFrame(animationRef.current.frameId);
    }
    animationRef.current.frameId = 0;
    animationRef.current.lastTimestamp = 0;
  };

  const snapToTarget = (targetSnapshot) => {
    displayValuesRef.current = targetSnapshot;
    setDisplayValues(targetSnapshot);
  };

  const scheduleAnimation = (key) => {
    if (animationRef.current.frameId || typeof requestAnimationFrame !== "function") {
      return;
    }

    const stepAnimation = (timestamp) => {
      if (animationRef.current.key !== key) {
        animationRef.current.frameId = 0;
        animationRef.current.lastTimestamp = 0;
        return;
      }

      const timestampMs = toFiniteNumber(timestamp, animationNowMs());
      const lastTimestamp = animationRef.current.lastTimestamp || Math.max(timestampMs - 16, 0);
      const deltaMs = Math.min(Math.max(timestampMs - lastTimestamp, 0), 50);
      animationRef.current.lastTimestamp = timestampMs;

      const { values, done } = advanceUrdfJointValues(
        displayValuesRef.current,
        targetValuesRef.current,
        deltaMs,
        URDF_JOINT_ANIMATION_FOLLOW_MS / animationSpeed,
        undefined,
        wrappedJointNames
      );
      displayValuesRef.current = values;
      setDisplayValues(values);

      if (done) {
        animationRef.current.frameId = 0;
        animationRef.current.lastTimestamp = 0;
        return;
      }

      animationRef.current.frameId = requestAnimationFrame(stepAnimation);
    };

    animationRef.current.frameId = requestAnimationFrame(stepAnimation);
  };

  useEffect(() => {
    const nextKey = String(animationKey || "");
    const targetSnapshot = cloneJointValueMap(targetValues);
    const keyChanged = animationRef.current.key !== nextKey;
    targetValuesRef.current = targetSnapshot;

    if (keyChanged) {
      cancelAnimation();
      animationRef.current.key = nextKey;
      snapToTarget(targetSnapshot);
      return undefined;
    }

    if (!nextKey || typeof requestAnimationFrame !== "function") {
      cancelAnimation();
      snapToTarget(targetSnapshot);
      return undefined;
    }

    if (jointValueMapsClose(displayValuesRef.current, targetSnapshot)) {
      cancelAnimation();
      snapToTarget(targetSnapshot);
      return undefined;
    }

    scheduleAnimation(nextKey);
    return undefined;
  }, [animationKey, animationSpeed, targetValues, wrappedJointNames]);

  useEffect(() => () => {
    cancelAnimation();
  }, []);

  return displayValues;
}

function meshAssetKeyForEntry(entry) {
  return entry?.kind === "stl" ? "stl" : "glb";
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
  const referenceHash = entryAssetHash(entry, "topology") || String(entry?.step?.hash || "");
  return fileRef && referenceHash ? `${fileRef}:${referenceHash}` : "";
}

function buildDxfCacheKey(entry) {
  const fileRef = fileKey(entry);
  const dxfHash = entryAssetHash(entry, "dxf");
  return fileRef && dxfHash ? `${fileRef}:${dxfHash}` : "";
}

function buildUrdfCacheKey(entry) {
  const fileRef = fileKey(entry);
  const urdfHash = entryAssetHash(entry, "urdf");
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

function buildCadCommand(fileRef, entry = null) {
  const sourceFormat = entrySourceFormat(entry);
  if (sourceFormat === RENDER_FORMAT.DXF) {
    return `${CAD_BUILD_COMMANDS.dxf} ${fileRef}`;
  }
  if (sourceFormat === RENDER_FORMAT.URDF) {
    return `${CAD_BUILD_COMMANDS.urdf} ${fileRef}`;
  }
  if (sourceFormat === RENDER_FORMAT.STL) {
    return "";
  }
  const command = entry?.kind === "assembly" ? CAD_BUILD_COMMANDS.stepAssembly : CAD_BUILD_COMMANDS.stepPart;
  return `${command} ${fileRef}`;
}

function entryHasMesh(entry) {
  if (entry?.kind === "assembly") {
    return Boolean(
      entryAssetUrl(entry, "topology") &&
      entryAssetHash(entry, "topology") &&
      entryAssetUrl(entry, "glb") &&
      entryAssetHash(entry, "glb")
    );
  }
  const meshKey = meshAssetKeyForEntry(entry);
  return Boolean(entryAssetUrl(entry, meshKey) && entryAssetHash(entry, meshKey));
}

function entryHasUrdf(entry) {
  return Boolean(entryAssetUrl(entry, "urdf") && entryAssetHash(entry, "urdf"));
}

function entryHasReferences(entry) {
  return Boolean(
    entryAssetUrl(entry, "topology") &&
    entryAssetUrl(entry, "topologyBinary") &&
    entryAssetHash(entry, "topology") &&
    entryAssetHash(entry, "topologyBinary")
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
  if (kind === RENDER_FORMAT.URDF) {
    return RENDER_FORMAT.URDF;
  }
  return RENDER_FORMAT.STEP;
}

function fileSheetKindForEntry(entry) {
  const kind = String(entry?.kind || "").trim().toLowerCase();
  if (kind === "dxf") {
    return "dxf";
  }
  if (kind === "urdf") {
    return "urdf";
  }
  if (kind === "assembly") {
    return "stepAssembly";
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
    edges: Math.max(0, Number(referencePayload?.manifest?.stats?.edgeCount || 0)),
    vertices: Math.max(0, Number(referencePayload?.manifest?.stats?.vertexCount || 0))
  };
}

function buildNormalizedReferenceState(entry, referencePayload = null, {
  copyCadPath,
  partId = "",
  transform = null,
  remapOccurrenceId = ""
} = {}) {
  const counts = readReferenceCounts(referencePayload);

  const selectorRuntime = buildSelectorRuntime(referencePayload, {
    copyCadPath: copyCadPath || cadPathForEntry(entry),
    partId,
    transform,
    remapOccurrenceId
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
      edges: Number(selectorRuntime.edges?.length || 0),
      vertices: Number(selectorRuntime.vertices?.length || 0)
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
    missingPartNames
  };
}

function buildSelectionCopyButtonLabel(lines, { limit = 3 } = {}) {
  const copyLines = Array.isArray(lines) ? lines : [];
  const normalizedLimit = Math.max(1, Number(limit) || 1);
  const tokens = copyLines
    .map((line) => parseCadRefToken(String(line || "").trim())?.token || String(line || "").trim())
    .filter(Boolean);

  if (!tokens.length) {
    return "Copy refs";
  }

  const visibleTokens = tokens.slice(0, normalizedLimit);
  const remainingCount = tokens.length - visibleTokens.length;
  return remainingCount > 0
    ? `Copy ${visibleTokens.join(", ")} and ${remainingCount} other${remainingCount === 1 ? "" : "s"}`
    : `Copy ${visibleTokens.join(", ")}`;
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

function finiteNumberOrNull(value) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : null;
}

function mergeMeasurementBounds(boundsList) {
  const normalizedBounds = (Array.isArray(boundsList) ? boundsList : [])
    .filter((bounds) => Array.isArray(bounds?.min) && Array.isArray(bounds?.max));
  if (!normalizedBounds.length) {
    return null;
  }
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (const bounds of normalizedBounds) {
    for (let index = 0; index < 3; index += 1) {
      const minValue = Number(bounds.min[index]);
      const maxValue = Number(bounds.max[index]);
      if (!Number.isFinite(minValue) || !Number.isFinite(maxValue)) {
        continue;
      }
      min[index] = Math.min(min[index], minValue);
      max[index] = Math.max(max[index], maxValue);
    }
  }
  return min.every(Number.isFinite) && max.every(Number.isFinite) ? { min, max } : null;
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

function buildViewerMeshAlert(entry, hasMeshData, loadError) {
  const fileRef = fileKey(entry);
  if (!fileRef) {
    return null;
  }

  const sourceFormat = entrySourceFormat(entry);
  const command = buildCadCommand(fileRef, entry);
  const reloadResolution = sourceFormat === RENDER_FORMAT.STL
    ? "Confirm the STL exists in the repo and reload the page."
    : "Try reloading the page. If the problem persists, rebuild the render assets for this entry.";
  const missingResolution = sourceFormat === RENDER_FORMAT.STL
    ? "Confirm the STL exists in the repo and reload the page."
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

function buildViewerDxfAlert(fileRef, hasDxfData, loadError, previewError) {
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
      message: "The selected entry does not have a ready DXF companion asset for the flat-pattern viewer.",
      resolution: "Rebuild the CAD assets for this entry, then reload the page.",
      command
    };
  }

  return null;
}

export default function CadWorkspace({
  manifestEntries: manifestEntriesProp = [],
  catalogRootName = "models",
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
  const [dxfBendSettingsLoadedFileRef, setDxfBendSettingsLoadedFileRef] = useState("");
  const [referenceQuery, setReferenceQuery] = useState("");
  const [selectedReferenceIds, setSelectedReferenceIds] = useState([]);
  const [hoveredListReferenceId, setHoveredListReferenceId] = useState("");
  const [hoveredModelReferenceId, setHoveredModelReferenceId] = useState("");
  const [selectedPartIds, setSelectedPartIds] = useState([]);
  const [selectedRenderPartIdByAssemblyPartId, setSelectedRenderPartIdByAssemblyPartId] = useState({});
  const [selectedWholeEntryCadRefToken, setSelectedWholeEntryCadRefToken] = useState("");
  const [expandedAssemblyPartIds, setExpandedAssemblyPartIds] = useState([]);
  const [hiddenPartIds, setHiddenPartIds] = useState([]);
  const [hoveredListPartId, setHoveredListPartId] = useState("");
  const [hoveredModelPartId, setHoveredModelPartId] = useState("");
  const [copyStatus, setCopyStatus] = useState("");
  const [stepUpdateInProgress, setStepUpdateInProgress] = useState(false);
  const [screenshotStatus, setScreenshotStatus] = useState("");
  const [persistenceStatus, setPersistenceStatus] = useState("");
  const [tabToolsOpen, setTabToolsOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(DEFAULT_SIDEBAR_WIDTH);
  const [isDesktop, setIsDesktop] = useState(false);
  const [viewerAlertOpen, setViewerAlertOpen] = useState(false);
  const [viewerRuntimeAlert, setViewerRuntimeAlert] = useState(null);
  const [lookMenuOpen, setLookMenuOpen] = useState(false);
  const [lookSettings, setLookSettings] = useState(readLookSettings);
  const [cadWorkspaceGlassTone, setCadWorkspaceGlassTone] = useState(readCadWorkspaceGlassTone);
  const [previewMode, setPreviewMode] = useState(false);
  const [tabToolsWidth, setTabToolsWidth] = useState(DEFAULT_TAB_TOOLS_WIDTH);
  const [drawingTool, setDrawingTool] = useState(DRAWING_TOOL.FREEHAND);
  const [viewerPerspective, setViewerPerspective] = useState(null);
  const [tabToolMode, setTabToolMode] = useState(TAB_TOOL_MODE.REFERENCES);
  const [measurementReferenceIds, setMeasurementReferenceIds] = useState([]);
  const [measurementResult, setMeasurementResult] = useState(null);
  const [measurementAnchor, setMeasurementAnchor] = useState(null);
  const [measurementHistory, setMeasurementHistory] = useState([]);
  const [measureDensity, setMeasureDensity] = useState(DEFAULT_MEASURE_DENSITY_G_CM3);
  const [drawingStrokes, setDrawingStrokes] = useState([]);
  const [drawingUndoStack, setDrawingUndoStack] = useState([]);
  const [drawingRedoStack, setDrawingRedoStack] = useState([]);
  const [jointValuesByFileRef, setJointValuesByFileRef] = useState({});
  const [urdfAnimationSettingsByFileRef, setUrdfAnimationSettingsByFileRef] = useState({});
  const [urdfEntryAnimationEnabled, setUrdfEntryAnimationEnabled] = useState(DEFAULT_URDF_ANIMATION_SETTINGS.introEnabled);
  const [selectedUrdfIntroReplayToken, setSelectedUrdfIntroReplayToken] = useState(0);
  const [pendingCadRefQueryParams, setPendingCadRefQueryParams] = useState(() => readCadRefQueryParams());
  const [inspectedAssemblyReferenceState, setInspectedAssemblyReferenceState] = useState(null);
  const [, setInspectedAssemblyReferenceStatus] = useState(REFERENCE_STATUS.IDLE);
  const [, setInspectedAssemblyReferenceError] = useState("");
  const lastPersistenceFailureKeyRef = useRef("");
  const measurementHistoryIdRef = useRef(0);

  const handlePersistenceWriteError = useCallback(({ key }) => {
    const failureKey = String(key || "browser-storage");
    if (lastPersistenceFailureKeyRef.current === failureKey) {
      return;
    }
    lastPersistenceFailureKeyRef.current = failureKey;
    setPersistenceStatus("Browser storage could not save CAD Explorer state.");
  }, []);

  const entryMap = useMemo(() => {
    const map = new Map();
    for (const entry of catalogEntries) {
      map.set(fileKey(entry), entry);
    }
    return map;
  }, [catalogEntries]);

  const {
    meshState,
    setMeshState,
    meshLoadInProgress,
    meshLoadTargetFile,
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
    urdfState,
    setUrdfState,
    urdfStatus,
    setUrdfStatus,
    urdfError,
    setUrdfError,
    referenceState,
    setReferenceState,
    setReferenceStatus,
    setReferenceError,
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
  const selectedEntrySourceFormat = entrySourceFormat(selectedEntry);
  const selectedFileSheetKind = fileSheetKindForEntry(selectedEntry);
  const isAssemblyView = selectedEntry?.kind === "assembly";
  const isUrdfView = selectedEntry?.kind === "urdf";
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
    urdfState.urdfHash === entryAssetHash(selectedEntry, "urdf");
  const selectedUrdfData = selectedUrdfMatches ? urdfState.urdfData : null;
  const selectedUrdfMeshes = selectedUrdfMatches ? urdfState.meshesByUrl : null;
  const selectedDxfData = selectedDxfMatches ? dxfState.dxfData : null;
  const selectedDxfFileRef = selectedEntrySourceFormat === RENDER_FORMAT.DXF
    ? fileKey(selectedEntry)
    : "";
  const selectedUrdfFileRef = selectedEntrySourceFormat === RENDER_FORMAT.URDF
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
  const selectedUrdfAnimationSettings = useMemo(() => {
    return {
      introEnabled: normalizeUrdfIntroAnimationEnabled(urdfEntryAnimationEnabled),
      speed: selectedUrdfFileRef
        ? normalizeUrdfAnimationSpeed(urdfAnimationSettingsByFileRef?.[selectedUrdfFileRef]?.speed)
        : DEFAULT_URDF_ANIMATION_SETTINGS.speed
    };
  }, [selectedUrdfFileRef, urdfAnimationSettingsByFileRef, urdfEntryAnimationEnabled]);
  const selectedUrdfPoses = useMemo(
    () => (
      Array.isArray(selectedUrdfData?.poses)
        ? selectedUrdfData.poses.map((pose) => ({
          ...pose,
          resolvedJointValues: {
            ...defaultSelectedUrdfJointValues,
            ...(pose?.jointValuesByName && typeof pose.jointValuesByName === "object" ? pose.jointValuesByName : {})
          }
        }))
        : []
    ),
    [defaultSelectedUrdfJointValues, selectedUrdfData]
  );
  const activeSelectedUrdfPoseName = useMemo(
    () => (
      selectedUrdfPoses.find((pose) => jointValueMapsClose(selectedUrdfJointValues, pose.resolvedJointValues))?.name || ""
    ),
    [selectedUrdfJointValues, selectedUrdfPoses]
  );
  const selectedUrdfAnimationKey = selectedUrdfFileRef
    ? `${selectedUrdfFileRef}:${entryAssetHash(selectedEntry, "urdf") || ""}`
    : "";
  const selectedUrdfIntroOrderByLink = useMemo(
    () => buildUrdfLinkIntroOrderMap(selectedUrdfData),
    [selectedUrdfData]
  );
  const selectedUrdfWrappedJointNames = useMemo(
    () => buildUrdfWrappedJointNameSet(selectedUrdfData),
    [selectedUrdfData]
  );
  const animatedSelectedUrdfJointValues = useAnimatedUrdfJointValues(
    selectedUrdfJointValues,
    selectedUrdfAnimationKey,
    selectedUrdfAnimationSettings,
    selectedUrdfWrappedJointNames
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
      const posedPreview = poseUrdfMeshData(
        selectedUrdfData,
        selectedUrdfMeshGeometryResult.meshData,
        animatedSelectedUrdfJointValues
      );
      selectedUrdfMeshGeometryResult.meshData.parts = posedPreview.meshData.parts.map((part) => ({
        ...part,
        introOrder: selectedUrdfIntroOrderByLink.get(String(part?.linkName || "").trim()) ?? 0
      }));
      selectedUrdfMeshGeometryResult.meshData.bounds = posedPreview.meshData.bounds;
      return {
        ...posedPreview,
        meshData: selectedUrdfMeshGeometryResult.meshData,
        error: ""
      };
    } catch (error) {
      return {
        meshData: null,
        error: error instanceof Error ? error.message : String(error),
        linkWorldTransforms: new Map()
      };
    }
  }, [animatedSelectedUrdfJointValues, selectedUrdfData, selectedUrdfIntroOrderByLink, selectedUrdfMeshGeometryResult]);
  const selectedMeshData = selectedEntrySourceFormat === RENDER_FORMAT.URDF
    ? selectedUrdfPreview.meshData
    : selectedMeshMatches
      ? meshState.meshData
      : null;
  const assemblyRoot = selectedAssemblyStructureReady
    ? selectedMeshData?.assemblyRoot || null
    : null;
  const assemblyLeafParts = useMemo(() => {
    return Array.isArray(selectedMeshData?.parts) ? selectedMeshData.parts : flattenAssemblyLeafParts(assemblyRoot);
  }, [assemblyRoot, selectedMeshData?.parts]);
  const assemblyNodes = useMemo(() => flattenAssemblyNodes(assemblyRoot), [assemblyRoot]);
  const assemblyCurrentNodeId = expandedAssemblyPartIds[expandedAssemblyPartIds.length - 1] || "root";
  const assemblyCurrentNode = useMemo(
    () => findAssemblyNode(assemblyRoot, assemblyCurrentNodeId) || assemblyRoot,
    [assemblyCurrentNodeId, assemblyRoot]
  );
  const assemblyBreadcrumbNodes = useMemo(
    () => assemblyBreadcrumb(assemblyRoot, assemblyCurrentNodeId),
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
  const assemblyPartsLoaded = selectedAssemblyStructureReady;
  const supportsPartSelection = isAssemblyView && assemblyPartsLoaded && assemblyLeafParts.length > 0;
  const assemblyPartMap = useMemo(() => {
    const map = new Map();
    for (const node of assemblyNodes) {
      map.set(node.id, node);
    }
    for (const part of assemblyLeafParts) {
      map.set(part.id, part);
    }
    return map;
  }, [assemblyLeafParts, assemblyNodes]);
  const validAssemblySelectionIds = useMemo(
    () => assemblyNodes.map((node) => String(node?.id || "").trim()).filter(Boolean),
    [assemblyNodes]
  );
  const validAssemblyLeafIds = useMemo(
    () => assemblyLeafParts.map((part) => String(part?.id || "").trim()).filter(Boolean),
    [assemblyLeafParts]
  );
  const validAssemblyLeafIdSet = useMemo(
    () => new Set(validAssemblyLeafIds),
    [validAssemblyLeafIds]
  );
  const renderPartIdsForAssemblySelection = useCallback((partId, fallbackPartId = "") => {
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
  const defaultSelectedDxfBendSettings = useMemo(() => {
    if (!selectedDxfData) {
      return [];
    }
    try {
      return normalizeDxfBendSettings(selectedDxfData, null);
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
  const urdfViewerLoading =
    !!selectedEntry &&
    urdfStatus !== ASSET_STATUS.ERROR &&
    (!selectedUrdfMatches || urdfStatus === ASSET_STATUS.LOADING);
  const stepViewerLoading =
    !!selectedEntry &&
    status !== ASSET_STATUS.ERROR &&
    (!selectedMeshMatches || status === ASSET_STATUS.LOADING);
  const viewerLoading = effectiveRenderFormat === RENDER_FORMAT.DXF
    ? dxfViewerLoading
    : effectiveRenderFormat === RENDER_FORMAT.URDF
      ? urdfViewerLoading
      : stepViewerLoading;
  const assemblySidebarLoading =
    isAssemblyView &&
    selectedMeshMatches &&
    !assemblyPartsLoaded &&
    !selectedAssemblyHydrationFailed;
  const viewerLoadingLabel = effectiveRenderFormat === RENDER_FORMAT.DXF
    ? selectedEntry && !selectedEntryHasDxf
      ? "Generating DXF preview..."
      : "Loading DXF preview..."
    : effectiveRenderFormat === RENDER_FORMAT.URDF
      ? "Loading URDF robot..."
      : effectiveRenderFormat === RENDER_FORMAT.STL
        ? "Loading STL..."
      : stepUpdateInProgress
        ? "STEP changed. Updating/regenerating CAD..."
        : selectedEntry && !selectedEntryHasMesh
          ? "Generating CAD assets..."
          : "Loading CAD...";
  const viewerAlert = useMemo(() => {
    if (!selectedEntry || viewerLoading) {
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
    if (effectiveRenderFormat === RENDER_FORMAT.URDF) {
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
    selectedDxfData,
    selectedEntry,
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
      setDxfBendSettingsLoadedFileRef("");
      setDxfBendSettings([]);
      return;
    }
    const storedSettings = readDxfBendOverridesForEntry(selectedDxfFileRef);
    setDxfBendSettings(normalizeDxfBendSettings(selectedDxfData, storedSettings?.bends));
    setDxfBendSettingsLoadedFileRef(selectedDxfFileRef);
  }, [selectedDxfData, selectedDxfFileRef]);
  useEffect(() => {
    if (
      !selectedDxfFileRef ||
      !selectedDxfData ||
      dxfBendSettingsLoadedFileRef !== selectedDxfFileRef
    ) {
      return;
    }
    writeDxfBendOverridesForEntry(
      selectedDxfFileRef,
      dxfBendSettingsEqual(normalizedSelectedDxfBendSettings, defaultSelectedDxfBendSettings)
        ? null
        : { bends: normalizedSelectedDxfBendSettings },
      { onWriteError: handlePersistenceWriteError }
    );
  }, [
    defaultSelectedDxfBendSettings,
    dxfBendSettingsLoadedFileRef,
    handlePersistenceWriteError,
    normalizedSelectedDxfBendSettings,
    selectedDxfData,
    selectedDxfFileRef
  ]);
  const viewerInAssemblyMode =
    isAssemblyView &&
    String(assemblyCurrentNode?.nodeType || "assembly").trim() === "assembly";
  const viewerMode = viewerInAssemblyMode ? "assembly" : "part";
  const drawModeActive = selectedEntrySourceFormat === RENDER_FORMAT.STEP && tabToolMode === TAB_TOOL_MODE.DRAW;
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
  const viewportReadyRef = useRef(false);
  const viewerRef = useRef(null);
  const previewUiStateRef = useRef(null);
  const panelResizeStateRef = useRef(null);
  const openTabsRef = useRef(openTabs);
  const activePerspectiveRef = useRef(null);
  const cadWorkspaceSessionPersistTimeoutRef = useRef(0);
  const buildPersistedCadWorkspaceSessionRef = useRef(null);
  const tabToolsResizeStateRef = useRef(null);
  const selectedFileSheetKeyRef = useRef("");
  const restoredCadWorkspaceSessionRef = useRef(false);
  const cadWorkspaceSessionBootstrappedRef = useRef(false);
  const cadWorkspaceSessionPersistenceReadyRef = useRef(false);

  useEffect(() => {
    openTabsRef.current = openTabs;
  }, [openTabs]);

  const updateLookSettings = useCallback((updater) => {
    setLookSettings((current) => {
      const next = typeof updater === "function" ? updater(current) : updater;
      return normalizeLookSettings(next);
    });
  }, []);

  const handleResetLookSettings = useCallback(() => {
    setLookSettings(cloneLookSettings(DEFAULT_LOOK_SETTINGS));
    setCadWorkspaceGlassTone(CAD_WORKSPACE_DEFAULT_GLASS_TONE);
  }, []);

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
    if (!isDesktop || !sidebarOpen) {
      return;
    }

    event.preventDefault();
    const nextWidth = sidebarWidth;
    document.querySelector("[data-slot='sidebar-wrapper']")?.setAttribute("data-sidebar-resizing", "true");
    panelResizeStateRef.current = {
      startX: event.clientX,
      startWidth: nextWidth,
      latestWidth: nextWidth,
      animationFrame: 0
    };
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [isDesktop, sidebarOpen, sidebarWidth]);

  const handleSidebarOpenChange = useCallback((value) => {
    setSidebarOpen((current) => {
      const nextOpen = typeof value === "function" ? value(current) : value;
      if (!current && nextOpen) {
        setSidebarWidth(DEFAULT_SIDEBAR_WIDTH);
      }
      return nextOpen;
    });
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
      hiddenPartIds,
      perspective: activePerspectiveRef.current,
      drawingTool,
      tabToolsOpen,
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
    hiddenPartIds,
    referenceQuery,
    selectedPartIds,
    selectedReferenceIds,
    tabToolMode,
    tabToolsOpen
  ]);

  const buildPersistedCadWorkspaceSession = useCallback(() => {
    const nextOpenTabs = selectedKey
      ? upsertTabRecord(openTabs, selectedKey, buildActiveTabSnapshot())
      : openTabs;
    return buildCadWorkspaceSessionState({
      openTabs: nextOpenTabs,
      selectedKey,
      query,
      expandedDirectoryIds: Array.from(expandedDirectoryIds),
      sidebarOpen,
      sidebarWidth,
      tabToolsWidth,
      urdfEntryAnimationEnabled
    });
  }, [
    buildActiveTabSnapshot,
    expandedDirectoryIds,
    openTabs,
    query,
    selectedKey,
    sidebarOpen,
    sidebarWidth,
    tabToolsWidth,
    urdfEntryAnimationEnabled,
    upsertTabRecord
  ]);

  useEffect(() => {
    buildPersistedCadWorkspaceSessionRef.current = buildPersistedCadWorkspaceSession;
  }, [buildPersistedCadWorkspaceSession]);

  const flushCadWorkspaceSessionPersistence = useCallback(() => {
    if (!cadWorkspaceSessionPersistenceReadyRef.current) {
      return;
    }
    const buildSnapshot = buildPersistedCadWorkspaceSessionRef.current;
    if (!buildSnapshot) {
      return;
    }
    writeCadWorkspaceSessionState(buildSnapshot(), { onWriteError: handlePersistenceWriteError });
  }, [handlePersistenceWriteError]);

  const scheduleCadWorkspaceSessionPersistence = useCallback(() => {
    if (!cadWorkspaceSessionPersistenceReadyRef.current) {
      return;
    }
    if (cadWorkspaceSessionPersistTimeoutRef.current) {
      return;
    }
    cadWorkspaceSessionPersistTimeoutRef.current = window.setTimeout(() => {
      cadWorkspaceSessionPersistTimeoutRef.current = 0;
      flushCadWorkspaceSessionPersistence();
    }, CAD_WORKSPACE_SESSION_PERSIST_DELAY_MS);
  }, [flushCadWorkspaceSessionPersistence]);

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

  const applyTabRecord = useCallback((tabRecord) => {
    const nextTab = createTabRecord(tabRecord?.key || "", tabRecord || {});
    const nextPerspective = clonePerspectiveSnapshot(nextTab.perspective);
    setDxfThicknessMm(nextTab.dxfThicknessMm);
    setReferenceQuery(nextTab.referenceQuery);
    selectedReferenceIdsRef.current = nextTab.selectedReferenceIds;
    setSelectedReferenceIds(nextTab.selectedReferenceIds);
    selectedPartIdsRef.current = nextTab.selectedPartIds;
    setSelectedPartIds(nextTab.selectedPartIds);
    setSelectedRenderPartIdByAssemblyPartId({});
    setSelectedWholeEntryCadRefToken("");
    setExpandedAssemblyPartIds(nextTab.expandedAssemblyPartIds);
    setHiddenPartIds(nextTab.hiddenPartIds);
    setHoveredListReferenceId("");
    setHoveredModelReferenceId("");
    setHoveredListPartId("");
    setHoveredModelPartId("");
    setCopyStatus("");
    setScreenshotStatus("");
    setTabToolsOpen(nextTab.tabToolsOpen);
    setTabToolMode(nextTab.tabToolMode);
    setDrawingTool(nextTab.drawingTool);
    activePerspectiveRef.current = nextPerspective;
    setViewerPerspective(nextPerspective);
    setDrawingStrokes(nextTab.drawingStrokes);
    setDrawingUndoStack(nextTab.drawingUndoStack);
    setDrawingRedoStack(nextTab.drawingRedoStack);
    setSelectedKey(nextTab.key);
  }, []);

  const resetActiveWorkspace = useCallback(() => {
    selectedReferenceIdsRef.current = [];
    selectedPartIdsRef.current = [];
    setSelectedWholeEntryCadRefToken("");
    setDxfBendSettingsLoadedFileRef("");
    setDxfThicknessMm(0);
    setDxfBendSettings([]);
    setReferenceQuery("");
    setSelectedReferenceIds([]);
    setSelectedPartIds([]);
    setSelectedRenderPartIdByAssemblyPartId({});
    setExpandedAssemblyPartIds([]);
    setHiddenPartIds([]);
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
  }, []);

  const activateEntryTab = useCallback((key) => {
    if (!key || !entryMap.has(key)) {
      return;
    }
    if (key === selectedKey) {
      return;
    }

    const nextTabs = openTabsRef.current;
    const nextEntry = entryMap.get(key);
    const nextTab = nextTabs.find((tab) => tab.key === key) || createTabRecord(key, {
      drawingTool: selectedKey ? drawingTool : DRAWING_TOOL.FREEHAND,
      tabToolsOpen: isDesktop && !!fileSheetKindForEntry(nextEntry),
      tabToolMode: selectedKey ? tabToolMode : TAB_TOOL_MODE.REFERENCES
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
  }, [
    applyTabRecord,
    buildActiveTabSnapshot,
    drawingTool,
    entryMap,
    getCachedDxfState,
    getCachedMeshState,
    getCachedReferenceState,
    getCachedUrdfState,
    isDesktop,
    selectedKey,
    setDxfError,
    setDxfState,
    setDxfStatus,
    setUrdfError,
    setUrdfState,
    setUrdfStatus,
    tabToolMode,
    tabToolsOpen,
    upsertTabRecord
  ]);

  useCadWorkspaceSession({
    manifestEntries,
    fileKey,
    readCadWorkspaceSessionState,
    restoredCadWorkspaceSessionRef,
    cadWorkspaceSessionBootstrappedRef,
    cadWorkspaceSessionPersistenceReadyRef,
    setQuery,
    setExpandedDirectoryIds,
    setSidebarOpen,
    setSidebarWidth,
    setTabToolsWidth,
    setUrdfEntryAnimationEnabled,
    setOpenTabs,
    applyTabRecord,
    selectedEntryKeyFromUrl,
    createTabRecord,
    initialSelectedTabSnapshot: {
      drawingTool: DRAWING_TOOL.FREEHAND,
      tabToolsOpen: false,
      tabToolMode: TAB_TOOL_MODE.REFERENCES
    },
    upsertTabRecord,
    buildPersistedCadWorkspaceSession,
    scheduleCadWorkspaceSessionPersistence,
    flushCadWorkspaceSessionPersistence,
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
    writeCadParam
  });

  useEffect(() => {
    applyThemeToDocument(DARK_THEME_ID, document.documentElement);
    writeThemePreference(DARK_THEME_ID, { onWriteError: handlePersistenceWriteError });
  }, [handlePersistenceWriteError]);

  useEffect(() => {
    writeLookSettings(lookSettings, { onWriteError: handlePersistenceWriteError });
  }, [handlePersistenceWriteError, lookSettings]);

  useEffect(() => {
    const normalizedTone = normalizeCadWorkspaceGlassTone(cadWorkspaceGlassTone);
    document.documentElement.dataset.glassTone = normalizedTone;
    writeCadWorkspaceGlassTone(normalizedTone, { onWriteError: handlePersistenceWriteError });
    return () => {
      delete document.documentElement.dataset.glassTone;
    };
  }, [handlePersistenceWriteError, cadWorkspaceGlassTone]);

  useEffect(() => {
    const handleStorage = (event) => {
      if (event.key !== LOOK_SETTINGS_STORAGE_KEY) {
        return;
      }
      if (!event.newValue) {
        setLookSettings(cloneLookSettings(DEFAULT_LOOK_SETTINGS));
        return;
      }
      try {
        const parsed = JSON.parse(event.newValue);
        setLookSettings(normalizeLookSettings(parsed));
      } catch (error) {
        console.warn("Failed to sync look settings from another tab", error);
      }
    };

    window.addEventListener("storage", handleStorage);
    return () => {
      window.removeEventListener("storage", handleStorage);
    };
  }, []);

  useEffect(() => {
    if (lookMenuOpen) {
      setTabToolsOpen(false);
    }
  }, [lookMenuOpen]);

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
      if (tabToolsOpen) {
        setTabToolsOpen(false);
      }
      return;
    }
    if (selectedFileSheetKeyRef.current === nextFileSheetKey) {
      return;
    }
    selectedFileSheetKeyRef.current = nextFileSheetKey;
    setTabToolsOpen(isDesktop);
  }, [isDesktop, selectedFileSheetKind, selectedKey, tabToolsOpen]);

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
    setViewerAlertOpen(false);
  }, [viewerAlertKey]);

  useEffect(() => {
    setViewerRuntimeAlert(null);
  }, [selectedKey]);

  const clampSidebarWidth = useCallback((value) => {
    const maxWidth = typeof window === "undefined"
      ? DESKTOP_SIDEBAR_MAX_WIDTH
      : Math.min(DESKTOP_SIDEBAR_MAX_WIDTH, Math.floor(window.innerWidth * 0.42));
    return clampPanelWidth(value, DESKTOP_SIDEBAR_MIN_WIDTH, maxWidth);
  }, []);

  const clampTabToolsWidth = useCallback((value) => {
    const maxWidth = typeof window === "undefined"
      ? DESKTOP_TAB_TOOLS_MAX_WIDTH
      : Math.min(DESKTOP_TAB_TOOLS_MAX_WIDTH, Math.floor(window.innerWidth * 0.42));
    return clampPanelWidth(value, DESKTOP_TAB_TOOLS_MIN_WIDTH, maxWidth);
  }, []);

  useCadWorkspaceLayout({
    restoredCadWorkspaceSessionRef,
    viewportReadyRef,
    hasSelectedEntry: Boolean(selectedKey),
    isDesktop,
    setIsDesktop,
    setSidebarOpen,
    setTabToolsOpen,
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
    if (selectedKey) {
      setMobileSidebarOpen(false);
      return undefined;
    }
    if (previewMode || typeof window === "undefined") {
      return undefined;
    }

    const mediaQuery = window.matchMedia(MOBILE_FILE_EXPLORER_MEDIA_QUERY);
    const openExplorerForEmptyMobileWorkspace = () => {
      if (mediaQuery.matches) {
        setMobileSidebarOpen(true);
      }
    };

    openExplorerForEmptyMobileWorkspace();
    mediaQuery.addEventListener("change", openExplorerForEmptyMobileWorkspace);
    return () => {
      mediaQuery.removeEventListener("change", openExplorerForEmptyMobileWorkspace);
    };
  }, [previewMode, selectedKey]);

  useEffect(() => {
    setCatalogEntries(manifestEntries);
  }, [manifestEntries]);

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
    if (![RENDER_FORMAT.STEP, RENDER_FORMAT.STL].includes(effectiveRenderFormat)) {
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
    if (effectiveRenderFormat !== RENDER_FORMAT.URDF) {
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
  const referenceLoadingEnabled =
    pendingCadRefQueryParams.length > 0 ||
    (effectiveRenderFormat === RENDER_FORMAT.STEP && selectedEntryHasReferences && !isAssemblyView);

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
    visibleReferences,
    filteredAssemblyParts
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
      const cachedBundle = loadRenderSelectorBundle(
        entryAssetUrl(selectedEntry, "topology"),
        entryAssetUrl(selectedEntry, "topologyBinary")
      );
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
    const cachedBundle = loadRenderSelectorBundle(
      entryAssetUrl(inspectedAssemblyPartEntry, "topology"),
      entryAssetUrl(inspectedAssemblyPartEntry, "topologyBinary")
    );

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
        remapOccurrenceId: String(inspectedAssemblyPart?.occurrenceId || inspectedAssemblyPart?.id || "").trim()
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
  const isCornerReference = useCallback((reference) => (
    String(reference?.selectorType || "").trim() === "vertex"
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
        return isFaceReference(reference) || isEdgeReference(reference) || isCornerReference(reference);
      });
    if (topologyReferences.length) {
      return topologyReferences;
    }
    return inspectedAssemblyPartReferences;
  }, [
    inspectedAssemblyPartId,
    inspectedAssemblyPartReferences,
    isCornerReference,
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

  const viewerPickableReferences = useMemo(() => {
    if (viewerInAssemblyMode) {
      return [];
    }
    return effectiveVisibleReferences;
  }, [effectiveVisibleReferences, viewerInAssemblyMode]);
  const viewerPickableFaces = useMemo(
    () => viewerPickableReferences.filter((reference) => isFaceReference(reference)),
    [isFaceReference, viewerPickableReferences]
  );
  const viewerPickableEdges = useMemo(
    () => viewerPickableReferences.filter((reference) => isEdgeReference(reference)),
    [isEdgeReference, viewerPickableReferences]
  );
  const viewerPickableVertices = useMemo(
    () => viewerPickableReferences.filter((reference) => isCornerReference(reference)),
    [isCornerReference, viewerPickableReferences]
  );
  const viewerSelectedPartIds = useMemo(() => {
    if (isAssemblyView && isInspectingAssemblyPart) {
      return [];
    }
    if (!isAssemblyView) {
      return selectedPartIds;
    }
    return uniqueStringList(
      selectedPartIds.flatMap((id) => renderPartIdsForAssemblySelection(
        id,
        selectedRenderPartIdByAssemblyPartId[String(id || "").trim()]
      ))
    );
  }, [
    isAssemblyView,
    isInspectingAssemblyPart,
    renderPartIdsForAssemblySelection,
    selectedPartIds,
    selectedRenderPartIdByAssemblyPartId
  ]);
  const viewerHoveredPartIds = useMemo(() => {
    if (!isAssemblyView || isInspectingAssemblyPart || !hoveredPartId) {
      return hoveredPartId;
    }
    const normalizedHoveredPartId = String(hoveredPartId || "").trim();
    const hoveredSelectionId = assemblyPickPartIdMap.get(normalizedHoveredPartId) || normalizedHoveredPartId;
    const highlightedPartIds = renderPartIdsForAssemblySelection(hoveredSelectionId, normalizedHoveredPartId);
    return highlightedPartIds.length ? highlightedPartIds : hoveredPartId;
  }, [
    assemblyPickPartIdMap,
    hoveredPartId,
    isAssemblyView,
    isInspectingAssemblyPart,
    renderPartIdsForAssemblySelection
  ]);

  const handleUrdfJointValueChange = useCallback((joint, nextValueDeg) => {
    const jointName = String(joint?.name || "").trim();
    if (!selectedUrdfFileRef || !jointName) {
      return;
    }
    const clampedValueDeg = clampJointValueDeg(joint, nextValueDeg);
    startTransition(() => {
      setJointValuesByFileRef((current) => {
        const currentEntryValues = current?.[selectedUrdfFileRef] && typeof current[selectedUrdfFileRef] === "object"
          ? current[selectedUrdfFileRef]
          : defaultSelectedUrdfJointValues;
        return {
          ...current,
          [selectedUrdfFileRef]: {
            ...currentEntryValues,
            [jointName]: clampedValueDeg
          }
        };
      });
    });
  }, [defaultSelectedUrdfJointValues, selectedUrdfFileRef]);
  const handleResetUrdfPose = useCallback(() => {
    if (!selectedUrdfFileRef) {
      return;
    }
    startTransition(() => {
      setJointValuesByFileRef((current) => {
        if (!current?.[selectedUrdfFileRef]) {
          return current;
        }
        const next = { ...current };
        delete next[selectedUrdfFileRef];
        return next;
      });
    });
  }, [selectedUrdfFileRef]);
  const handleSelectUrdfPose = useCallback((pose) => {
    if (!selectedUrdfFileRef || !pose?.resolvedJointValues || typeof pose.resolvedJointValues !== "object") {
      return;
    }
    const nextJointValues = cloneJointValueMap(pose.resolvedJointValues);
    startTransition(() => {
      setJointValuesByFileRef((current) => ({
        ...current,
        [selectedUrdfFileRef]: nextJointValues
      }));
    });
  }, [selectedUrdfFileRef]);
  const handleCopyUrdfJointAngles = useCallback(async () => {
    setScreenshotStatus("");
    if (!movableUrdfJoints.length) {
      setCopyStatus("No movable joints are available");
      return;
    }
    try {
      await copyTextToClipboard(buildUrdfJointAnglesCopyText(movableUrdfJoints, selectedUrdfJointValues));
      setCopyStatus("Copied joint angles");
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "Clipboard write failed");
    }
  }, [movableUrdfJoints, selectedUrdfJointValues]);
  const handleUrdfIntroAnimationEnabledChange = useCallback((nextEnabled) => {
    setUrdfEntryAnimationEnabled(normalizeUrdfIntroAnimationEnabled(nextEnabled));
  }, []);
  const handleReplayUrdfIntroAnimation = useCallback(() => {
    if (!selectedUrdfFileRef) {
      return;
    }
    startTransition(() => {
      setSelectedUrdfIntroReplayToken((current) => current + 1);
    });
  }, [selectedUrdfFileRef]);
  const handleUrdfAnimationSpeedChange = useCallback((nextSpeed) => {
    if (!selectedUrdfFileRef) {
      return;
    }
    const normalizedSpeed = normalizeUrdfAnimationSpeed(nextSpeed);
    startTransition(() => {
      setUrdfAnimationSettingsByFileRef((current) => ({
        ...current,
        [selectedUrdfFileRef]: {
          ...DEFAULT_URDF_ANIMATION_SETTINGS,
          ...(current?.[selectedUrdfFileRef] && typeof current[selectedUrdfFileRef] === "object"
            ? current[selectedUrdfFileRef]
            : {}),
          speed: normalizedSpeed
        }
      }));
    });
  }, [selectedUrdfFileRef]);

  useEffect(() => {
    setSelectedUrdfIntroReplayToken(0);
  }, [selectedUrdfFileRef]);
  const copySelectionPayload = useMemo(() => {
    const selectedReferencesForCopy = selectedReferenceIds
      .map((id) => effectiveActiveReferenceMap.get(id))
      .filter(Boolean);
    const selectedPartsForCopy = supportsPartSelection && !isInspectingAssemblyPart
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
    isInspectingAssemblyPart,
    selectedEntry,
    selectedPartIds,
    selectedReferenceIds,
    supportsPartSelection
  ]);
  const copyButtonLabel = useMemo(
    () => buildSelectionCopyButtonLabel(copySelectionPayload.lines),
    [copySelectionPayload.lines]
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
      assemblyParts,
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
    setHoveredListReferenceId("");
    setHoveredModelReferenceId("");
    setHoveredListPartId("");
    setHoveredModelPartId("");
    setCopyStatus("");
    setTabToolMode(TAB_TOOL_MODE.REFERENCES);
    setPendingCadRefQueryParams([]);
  }, [
    assemblyParts,
    assemblyPartsLoaded,
    catalogEntries,
    isAssemblyView,
    pendingCadRefQueryParams,
    selectedEntry,
    selectedEntryHasReferences,
    selectedReferencesMatch,
    selectedReferenceIdsRef,
    selectedPartIdsRef,
    visibleReferences
  ]);

  useEffect(() => {
    if (!cadWorkspaceSessionPersistenceReadyRef.current || pendingCadRefQueryParams.length) {
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
    cadWorkspaceSessionPersistenceReadyRef
  ]);

  const toggleReferenceSelection = useCallback((referenceId, { multiSelect = false } = {}) => {
    if (stepUpdateInProgress) {
      return;
    }
    const next = computeNextSelectionIds(selectedReferenceIdsRef.current, referenceId, { multiSelect });
    if (next.length && !isDesktop) {
      setSidebarOpen(false);
    }
    setSelectedWholeEntryCadRefToken("");
    selectedReferenceIdsRef.current = next;
    setSelectedReferenceIds(next);
  }, [isDesktop, stepUpdateInProgress]);

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
    const selectedPartsForCopy = supportsPartSelection && !isInspectingAssemblyPart
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
    isInspectingAssemblyPart,
    selectedEntry,
    setScreenshotStatus,
    supportsPartSelection,
    stepUpdateInProgress
  ]);

  const handleInspectAssemblyPart = useCallback((partId) => {
    const normalizedPartId = String(partId || "").trim();
    if (!normalizedPartId) {
      return;
    }
    const node = assemblyPartMap.get(normalizedPartId);
    if (!node) {
      return;
    }
    setViewerAlertOpen(false);
    setSelectedWholeEntryCadRefToken("");
    selectedPartIdsRef.current = [];
    setSelectedPartIds([]);
    setSelectedRenderPartIdByAssemblyPartId({});
    setHoveredListPartId("");
    setHoveredModelPartId("");
    resetReferenceInteractionState();
    setHiddenPartIds((current) => current.filter((id) => !descendantLeafPartIds(node).includes(id)));
    setExpandedAssemblyPartIds((current) => {
      const existingIndex = current.indexOf(normalizedPartId);
      if (existingIndex >= 0) {
        return current.slice(0, existingIndex + 1);
      }
      return [...current, normalizedPartId];
    });
  }, [assemblyPartMap, resetReferenceInteractionState]);

  const handleBackAssemblyInspection = useCallback(() => {
    setViewerAlertOpen(false);
    setHoveredListPartId("");
    setHoveredModelPartId("");
    resetReferenceInteractionState();
    setExpandedAssemblyPartIds((current) => current.slice(0, -1));
  }, [resetReferenceInteractionState]);

  const handleExitAssemblyPartInspection = useCallback(() => {
    setViewerAlertOpen(false);
    setHoveredListPartId("");
    setHoveredModelPartId("");
    resetReferenceInteractionState();
    setExpandedAssemblyPartIds([]);
  }, [resetReferenceInteractionState]);

  const togglePartSelection = useCallback((partId, { multiSelect = false, renderPartId = "" } = {}) => {
    if (stepUpdateInProgress) {
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
  }, [isDesktop, renderPartIdForAssemblySelection, stepUpdateInProgress]);

  const clearAssemblySelection = useCallback(() => {
    selectedPartIdsRef.current = [];
    selectedReferenceIdsRef.current = [];
    setSelectedWholeEntryCadRefToken("");
    setSelectedPartIds([]);
    setSelectedRenderPartIdByAssemblyPartId({});
    setSelectedReferenceIds([]);
    setCopyStatus("");
  }, []);

  const togglePartVisibility = useCallback((partId) => {
    const leafIds = descendantLeafPartIds(assemblyPartMap.get(partId) || null);
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
  }, [assemblyPartMap]);

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
      for (const partId of nextSelectedPartIds.flatMap((id) => descendantLeafPartIds(assemblyPartMap.get(id) || null))) {
        if (!partId || hidden.has(partId)) {
          continue;
        }
        hidden.add(partId);
        next.push(partId);
        changed = true;
      }
      return changed ? next : current;
    });
  }, [assemblyPartMap]);

  const handleShowAllHiddenParts = useCallback(() => {
    setHiddenPartIds((current) => (current.length > 1 ? [] : current));
  }, []);

  const handleModelHoverChange = useCallback((referenceId) => {
    if (viewerInAssemblyMode) {
      const pickedPartId = String(referenceId || "").trim();
      if (!pickedPartId) {
        setHoveredModelReferenceId("");
        setHoveredModelPartId("");
        return;
      }
      setHoveredModelReferenceId("");
      setHoveredModelPartId(assemblyPickPartIdMap.get(pickedPartId) || pickedPartId);
      return;
    }
    const nextReferenceId = String(referenceId || "").trim();
    setHoveredModelReferenceId(nextReferenceId);
  }, [assemblyPickPartIdMap, viewerInAssemblyMode]);

  const commitMeasurementResult = useCallback((result) => {
    setMeasurementResult(result);
    if (!result || !Number.isFinite(Number(result.value))) {
      return;
    }
    measurementHistoryIdRef.current += 1;
    const historyEntry = {
      id: `measurement:${measurementHistoryIdRef.current}`,
      title: String(result.title || "Measurement").trim(),
      formattedValue: formatMeasurementValue(result.value, result.unit || "mm"),
      detail: String(result.detail || "").trim()
    };
    setMeasurementHistory((current) => [historyEntry, ...current].slice(0, 30));
  }, []);

  const handleModelReferenceActivate = useCallback((referenceId, { multiSelect = false, clientX = null, clientY = null } = {}) => {
    if (stepUpdateInProgress) {
      return;
    }
    if (viewerInAssemblyMode) {
      const pickedPartId = String(referenceId || "").trim();
      const nextPartId = assemblyPickPartIdMap.get(pickedPartId) || pickedPartId;
      if (!nextPartId) {
        clearAssemblySelection();
        return;
      }
      togglePartSelection(nextPartId, { multiSelect, renderPartId: pickedPartId });
      return;
    }
    const nextReferenceId = String(referenceId || "").trim();
    if (tabToolMode === TAB_TOOL_MODE.MEASURE) {
      if (!nextReferenceId) {
        setMeasurementReferenceIds([]);
        commitMeasurementResult(null);
        setMeasurementAnchor(null);
        return;
      }
      const reference = effectiveActiveReferenceMap.get(nextReferenceId);
      if (!reference) {
        return;
      }
      const selectorType = String(reference?.selectorType || "").trim();
      if (selectorType === "vertex") {
        const previousVertexIds = measurementReferenceIds
          .filter((id) => effectiveActiveReferenceMap.get(id)?.selectorType === "vertex");
        const nextIds = previousVertexIds.length === 1 && previousVertexIds[0] !== nextReferenceId
          ? [previousVertexIds[0], nextReferenceId]
          : [nextReferenceId];
        setMeasurementReferenceIds(nextIds);
        commitMeasurementResult(measurementForReferences(nextIds.map((id) => effectiveActiveReferenceMap.get(id)).filter(Boolean)));
        setMeasurementAnchor(Number.isFinite(clientX) && Number.isFinite(clientY) ? { x: clientX, y: clientY } : null);
        return;
      }
      if (selectorType === "edge") {
        const previousLineEdgeIds = measurementReferenceIds.filter((id) => {
          const previousReference = effectiveActiveReferenceMap.get(id);
          return previousReference?.selectorType === "edge" &&
            String(previousReference?.pickData?.curveType || "").trim().toLowerCase() === "line";
        });
        const isLineEdge = String(reference?.pickData?.curveType || "").trim().toLowerCase() === "line";
        const nextIds = isLineEdge && previousLineEdgeIds.length === 1 && previousLineEdgeIds[0] !== nextReferenceId
          ? [previousLineEdgeIds[0], nextReferenceId]
          : [nextReferenceId];
        setMeasurementReferenceIds(nextIds);
        commitMeasurementResult(measurementForReferences(nextIds.map((id) => effectiveActiveReferenceMap.get(id)).filter(Boolean)));
        setMeasurementAnchor(Number.isFinite(clientX) && Number.isFinite(clientY) ? { x: clientX, y: clientY } : null);
        return;
      }
      if (selectorType === "face") {
        const previousPlanarFaceIds = measurementReferenceIds.filter((id) => {
          const previousReference = effectiveActiveReferenceMap.get(id);
          return previousReference?.selectorType === "face" &&
            String(previousReference?.pickData?.surfaceType || "").trim().toLowerCase() === "plane";
        });
        const isPlanarFace = String(reference?.pickData?.surfaceType || "").trim().toLowerCase() === "plane";
        const nextIds = isPlanarFace && previousPlanarFaceIds.length === 1 && previousPlanarFaceIds[0] !== nextReferenceId
          ? [previousPlanarFaceIds[0], nextReferenceId]
          : [nextReferenceId];
        setMeasurementReferenceIds(nextIds);
        commitMeasurementResult(measurementForReferences(nextIds.map((id) => effectiveActiveReferenceMap.get(id)).filter(Boolean)));
        setMeasurementAnchor(Number.isFinite(clientX) && Number.isFinite(clientY) ? { x: clientX, y: clientY } : null);
        return;
      }
      const nextMeasurement = measurementForReferences([reference]);
      setMeasurementReferenceIds([nextReferenceId]);
      commitMeasurementResult(nextMeasurement || {
        kind: "unsupported",
        title: "No measurement",
        value: null,
        detail: "Pick a surface, edge, circular/cylindrical feature, or two corners.",
        referenceIds: [nextReferenceId]
      });
      setMeasurementAnchor(Number.isFinite(clientX) && Number.isFinite(clientY) ? { x: clientX, y: clientY } : null);
      return;
    }
    if (!nextReferenceId) {
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
    commitMeasurementResult,
    effectiveActiveReferenceMap,
    assemblyPickPartIdMap,
    measurementReferenceIds,
    stepUpdateInProgress,
    tabToolMode,
    toggleReferenceSelection,
    togglePartSelection,
    viewerInAssemblyMode
  ]);

  const handleModelReferenceDoubleActivate = useCallback((referenceId) => {
    const pickedPartId = String(referenceId || "").trim();
    const nextPartId = assemblyPickPartIdMap.get(pickedPartId) || pickedPartId;

    if (viewerInAssemblyMode) {
      if (!nextPartId) {
        return;
      }
      handleInspectAssemblyPart(nextPartId);
      return;
    }

    if (!isAssemblyView || !isInspectingAssemblyPart || nextPartId) {
      return;
    }

    handleExitAssemblyPartInspection();
  }, [
    handleExitAssemblyPartInspection,
    handleInspectAssemblyPart,
    isAssemblyView,
    isInspectingAssemblyPart,
    assemblyPickPartIdMap,
    viewerInAssemblyMode
  ]);

  const handleSelectEntry = useCallback((key) => {
    activateEntryTab(key);
    if (!isDesktop) {
      setSidebarOpen(false);
    }
  }, [activateEntryTab, isDesktop]);

  const handleSelectTabToolMode = useCallback((mode) => {
    setViewerAlertOpen(false);
    const normalizedMode = mode === TAB_TOOL_MODE.DRAW
      ? TAB_TOOL_MODE.DRAW
      : mode === TAB_TOOL_MODE.MEASURE
        ? TAB_TOOL_MODE.MEASURE
        : TAB_TOOL_MODE.REFERENCES;
    setTabToolMode(normalizedMode);
    if (normalizedMode === TAB_TOOL_MODE.DRAW && drawingTool === DRAWING_TOOL.SURFACE_LINE) {
      setDrawingTool(DRAWING_TOOL.FREEHAND);
    }
  }, [drawingTool]);

  const handleToggleFileSheet = useCallback(() => {
    if (!selectedFileSheetKind) {
      return;
    }
    setLookMenuOpen(false);
    setViewerAlertOpen(false);
    setTabToolsOpen((current) => !current);
  }, [selectedFileSheetKind]);

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
      scheduleCadWorkspaceSessionPersistence();
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
  }, [scheduleCadWorkspaceSessionPersistence]);

  useEffect(() => {
    return () => {
      if (cadWorkspaceSessionPersistTimeoutRef.current) {
        window.clearTimeout(cadWorkspaceSessionPersistTimeoutRef.current);
        cadWorkspaceSessionPersistTimeoutRef.current = 0;
      }
      flushCadWorkspaceSessionPersistence();
    };
  }, [flushCadWorkspaceSessionPersistence]);

  useCadWorkspaceShortcuts({
    copyStatus,
    screenshotStatus,
    setCopyStatus,
    setScreenshotStatus,
    previewMode,
    viewerAlertOpen,
    lookSheetOpen: lookMenuOpen && !previewMode,
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
    setLookMenuOpen,
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
        throw new Error("Viewer not ready");
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
        throw new Error("Viewer not ready");
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
    if (effectiveRenderFormat === RENDER_FORMAT.DXF || viewerLoading || !selectedMeshData || previewMode) {
      return;
    }
    previewUiStateRef.current = {
      sidebarOpen,
      tabToolsOpen,
      tabToolMode,
      lookMenuOpen,
      viewerAlertOpen
    };
    setCopyStatus("");
    setScreenshotStatus("");
    setDrawingStrokes([]);
    setDrawingUndoStack([]);
    setDrawingRedoStack([]);
    setViewerAlertOpen(false);
    setLookMenuOpen(false);
    setSidebarOpen(false);
    setTabToolsOpen(false);
    setPreviewMode(true);
  }, [
    effectiveRenderFormat,
    previewMode,
    sidebarOpen,
    selectedMeshData,
    tabToolMode,
    tabToolsOpen,
    lookMenuOpen,
    viewerAlertOpen,
    viewerLoading
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
  const measureToolAvailable = effectiveRenderFormat === RENDER_FORMAT.STEP && !viewerInAssemblyMode;
  const measureToolActive = measureToolAvailable && tabToolMode === TAB_TOOL_MODE.MEASURE;
  const drawToolActive = drawModeActive;
  const displayedMeasurement = measurementResult
    ? {
      ...measurementResult,
      formattedValue: formatMeasurementValue(measurementResult.value, measurementResult.unit || "mm")
    }
    : null;
  const measureProperties = useMemo(() => {
    const shapes = Array.isArray(effectiveSelectorRuntime?.shapes) ? effectiveSelectorRuntime.shapes : [];
    const solidShapes = shapes.filter((shape) => String(shape?.kind || "").trim().toLowerCase() === "solid");
    const measuredShapes = solidShapes.length ? solidShapes : shapes;
    const volumeValues = measuredShapes.map((shape) => finiteNumberOrNull(shape?.volume)).filter((value) => value !== null);
    const areaValues = measuredShapes.map((shape) => finiteNumberOrNull(shape?.area)).filter((value) => value !== null);
    const shapeBounds = measuredShapes.map((shape) => shape?.bbox).filter(Boolean);
    const volume = volumeValues.length ? volumeValues.reduce((sum, value) => sum + value, 0) : null;
    const surfaceArea = areaValues.length ? areaValues.reduce((sum, value) => sum + value, 0) : null;
    const bounds = mergeMeasurementBounds(shapeBounds) || selectedMeshData?.bounds || null;
    const label = String(
      isAssemblyView && isInspectingAssemblyPart
        ? inspectedAssemblyPart?.name || inspectedAssemblyPart?.displayName || inspectedAssemblyPart?.id
        : selectedEntry?.file || selectedEntry?.label || selectedEntry?.name || "Active part"
    ).trim();
    return {
      label,
      volume,
      surfaceArea,
      bounds
    };
  }, [
    effectiveSelectorRuntime?.shapes,
    inspectedAssemblyPart?.displayName,
    inspectedAssemblyPart?.id,
    inspectedAssemblyPart?.name,
    isAssemblyView,
    isInspectingAssemblyPart,
    selectedEntry?.file,
    selectedEntry?.label,
    selectedEntry?.name,
    selectedMeshData?.bounds
  ]);
  const viewerSelectedReferenceIds = measureToolActive
    ? measurementReferenceIds
    : selectedReferenceIds;
  const selectionCount = selectionCountBase;
  const canUndoDrawing = drawingUndoStack.length > 0;
  const canRedoDrawing = drawingRedoStack.length > 0;
  const lookSheetOpen = lookMenuOpen && !previewMode;
  const measureSheetOpen = measureToolActive && !previewMode && !lookSheetOpen;
  const fileSheetOpen = !!selectedFileSheetKind && tabToolsOpen && !previewMode && !lookSheetOpen;
  const activeSidebarWidth = isDesktop && sidebarOpen && !previewMode
    ? clampSidebarWidth(sidebarWidth)
    : 0;
  const activeSheetWidth = isDesktop && (fileSheetOpen || lookSheetOpen || measureSheetOpen)
    ? DEFAULT_TAB_TOOLS_WIDTH
    : 0;
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
  const mobileCadBottomBarPosition = {
    left: "12px",
    right: "12px",
    bottom: "calc(env(safe-area-inset-bottom, 0px) + 0.75rem)"
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

  return (
    <SidebarProvider
      open={sidebarOpen}
      onOpenChange={handleSidebarOpenChange}
      mobileOpen={mobileSidebarOpen}
      onMobileOpenChange={setMobileSidebarOpen}
      data-glass-tone={normalizeCadWorkspaceGlassTone(cadWorkspaceGlassTone)}
      style={{ "--sidebar-width": `${clampSidebarWidth(sidebarWidth)}px` }}
      className="relative h-svh overflow-hidden bg-transparent"
    >
      <div className="fixed inset-0 z-0">
        <CadRenderPane
          viewerRef={viewerRef}
          renderFormat={effectiveRenderFormat}
          renderPartsIndividually={isUrdfView}
          selectedMeshData={selectedMeshData}
          selectedDxfData={selectedDxfData}
          selectedDxfMeshData={selectedDxfMeshData}
          selectedKey={selectedKey}
          selectedDxfKey={selectedDxfPreviewKey}
          viewerPerspective={viewerPerspective}
          viewerPerspectiveRef={activePerspectiveRef}
          lookSettings={lookSettings}
          previewMode={previewMode}
          isDesktop={isDesktop}
          viewportFrameInsets={viewportFrameInsets}
          viewerLoading={viewerLoading}
          viewerAlert={viewerAlert}
          stepUpdateInProgress={effectiveRenderFormat === RENDER_FORMAT.STEP && stepUpdateInProgress}
          viewPlaneOffsetRight={viewportFrameInsets.right + 16}
          viewerMode={viewerMode}
          assemblyParts={isAssemblyView && selectedAssemblyInteractionReady ? assemblyLeafParts : EMPTY_LIST}
          hiddenPartIds={hiddenPartIds}
          selectedPartIds={viewerSelectedPartIds}
          hoveredPartId={viewerHoveredPartIds}
          hoveredReferenceId={hoveredReferenceId}
          selectedReferenceIds={viewerSelectedReferenceIds}
          selectorRuntime={effectiveSelectorRuntime}
          pickableFaces={viewerPickableFaces}
          pickableEdges={viewerPickableEdges}
          pickableVertices={viewerPickableVertices}
          inspectedAssemblyPartId={isInspectingAssemblyPart ? inspectedAssemblyPartId : ""}
          drawToolActive={drawToolActive}
          drawingTool={drawingTool}
          drawingStrokes={drawingStrokes}
          handleDrawingStrokesChange={handleDrawingStrokesChange}
          handlePerspectiveChange={handlePerspectiveChange}
          handleModelHoverChange={handleModelHoverChange}
          handleModelReferenceActivate={handleModelReferenceActivate}
          handleModelReferenceDoubleActivate={handleModelReferenceDoubleActivate}
          handleViewerAlertChange={handleViewerAlertChange}
          selectionCount={selectionCount}
          copyButtonLabel={copyButtonLabel}
          handleCopySelection={handleCopySelection}
          handleScreenshotCopy={handleScreenshotCopy}
          measureToolActive={measureToolActive}
          measurementResult={displayedMeasurement}
          measurementAnchor={measurementAnchor}
          measurementSelectionCount={measurementReferenceIds.length}
          handleClearMeasurement={() => {
            setMeasurementReferenceIds([]);
            commitMeasurementResult(null);
            setMeasurementAnchor(null);
          }}
          partIntroAnimation={isUrdfView ? {
            enabled: selectedUrdfAnimationSettings.introEnabled,
            introKey: selectedUrdfAnimationKey,
            replayToken: selectedUrdfIntroReplayToken
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
        onStartResize={handleStartSidebarResize}
      />

      <SidebarInset className="pointer-events-none relative z-10 h-svh min-w-0 overflow-hidden bg-transparent">
        <CadWorkspaceTopBar
          previewMode={previewMode}
          lookMenuOpen={lookMenuOpen}
          sidebarLabelForEntry={sidebarLabelForEntry}
          selectedEntry={selectedEntry}
          setLookMenuOpen={setLookMenuOpen}
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
                isDesktop={isDesktop}
                sidebarOpen={false}
                renderFormat={effectiveRenderFormat}
                floatingCadToolbarPosition={floatingCadToolbarPosition}
                mobileCadBottomBarPosition={mobileCadBottomBarPosition}
                selectionToolActive={selectionToolActive}
                measureToolActive={measureToolActive}
                measureToolDisabled={!measureToolAvailable}
                drawToolActive={drawToolActive}
                handleSelectTabToolMode={handleSelectTabToolMode}
                viewerLoading={viewerLoading}
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
                handleScreenshotCopy={handleScreenshotCopy}
                handleScreenshotDownload={handleScreenshotDownload}
              />

              <CadWorkspaceAssemblyInspectPill
                previewMode={previewMode}
                inspectedAssemblyPart={inspectedAssemblyPart}
                toolbarHeight={0}
                onExit={handleExitAssemblyPartInspection}
              />

              <ViewerLoadingOverlay
                viewerLoading={viewerLoading}
                previewMode={previewMode}
              />
            </div>

            {selectedFileSheetKind === "dxf" ? (
              <DxfFileSheet
                key={`dxf:${selectedKey}`}
                open={fileSheetOpen}
                isDesktop={isDesktop}
                width={DEFAULT_TAB_TOOLS_WIDTH}
                valueMm={effectiveDxfThicknessMm}
                bendLines={selectedDxfBendLines}
                bendSettings={normalizedSelectedDxfBendSettings}
                hasDxfData={!!selectedDxfData}
                viewerLoading={viewerLoading}
                onThicknessChange={setDxfThicknessMm}
                onBendChange={handleDxfBendSettingChange}
              />
            ) : null}

            <MeasureFileSheet
              key={`measure:${selectedKey}`}
              open={measureSheetOpen}
              isDesktop={isDesktop}
              width={DEFAULT_TAB_TOOLS_WIDTH}
              properties={measureProperties}
              density={measureDensity}
              onDensityChange={setMeasureDensity}
              history={measurementHistory}
              onClearHistory={() => setMeasurementHistory([])}
            />

            {selectedFileSheetKind === "stepAssembly" ? (
              <StepAssemblyFileSheet
                key={`stepAssembly:${selectedKey}`}
                open={fileSheetOpen}
                isDesktop={isDesktop}
                width={DEFAULT_TAB_TOOLS_WIDTH}
                selectedEntry={selectedEntry}
                viewerLoading={viewerLoading || assemblySidebarLoading}
                isAssemblyView={isAssemblyView}
                assemblyParts={assemblyParts}
                assemblyBreadcrumbNodes={assemblyBreadcrumbNodes}
                filteredAssemblyParts={filteredAssemblyParts}
                selectedPartIds={selectedPartIds}
                hoveredPartId={hoveredPartId}
                hiddenPartIds={hiddenPartIds}
                togglePartSelection={togglePartSelection}
                clearAssemblySelection={clearAssemblySelection}
                setHoveredListPartId={setHoveredListPartId}
                handleInspectAssemblyPart={handleInspectAssemblyPart}
                handleBackAssemblyInspection={handleBackAssemblyInspection}
                handleExitAssemblyPartInspection={handleExitAssemblyPartInspection}
                togglePartVisibility={togglePartVisibility}
                hideSelectedParts={handleHideSelectedParts}
                showAllHiddenParts={handleShowAllHiddenParts}
                inspectedAssemblyPart={inspectedAssemblyPart}
              />
            ) : null}

            {selectedFileSheetKind === "urdf" ? (
              <UrdfFileSheet
                key={`urdf:${selectedKey}`}
                open={fileSheetOpen}
                isDesktop={isDesktop}
                width={DEFAULT_TAB_TOOLS_WIDTH}
                joints={movableUrdfJoints}
                poses={selectedUrdfPoses}
                activePoseName={activeSelectedUrdfPoseName}
                jointValues={selectedUrdfJointValues}
                onJointValueChange={handleUrdfJointValueChange}
                onPoseSelect={handleSelectUrdfPose}
                onCopyJointAngles={handleCopyUrdfJointAngles}
                introAnimationEnabled={selectedUrdfAnimationSettings.introEnabled}
                animationSpeed={selectedUrdfAnimationSettings.speed}
                onIntroAnimationEnabledChange={handleUrdfIntroAnimationEnabledChange}
                onReplayIntroAnimation={handleReplayUrdfIntroAnimation}
                onAnimationSpeedChange={handleUrdfAnimationSpeedChange}
                onResetPose={handleResetUrdfPose}
              />
            ) : null}

            <LookSettingsPopover
              open={lookSheetOpen}
              isDesktop={isDesktop}
              width={DEFAULT_TAB_TOOLS_WIDTH}
              lookSettings={lookSettings}
              cadWorkspaceGlassTone={normalizeCadWorkspaceGlassTone(cadWorkspaceGlassTone)}
              updateLookSettings={updateLookSettings}
              updateCadWorkspaceGlassTone={(nextTone) => setCadWorkspaceGlassTone(normalizeCadWorkspaceGlassTone(nextTone))}
              handleResetLookSettings={handleResetLookSettings}
            />
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
      </SidebarInset>
    </SidebarProvider>
  );
}

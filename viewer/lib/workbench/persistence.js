import { clonePerspectiveSnapshot, perspectiveSnapshotEqual } from "../perspective.js";
import {
  cloneLookSettings,
  DEFAULT_LOOK_PRESET,
  DEFAULT_LOOK_SETTINGS,
  normalizeLookSettings
} from "../lookSettings.js";
import { THEME_STORAGE_KEY } from "../themes.js";
import {
  normalizeDxfBendAngleDeg,
  normalizeDxfBendDirection
} from "../dxf/buildPreviewMesh.js";
import { DRAWING_TOOL, RENDER_FORMAT, TAB_TOOL_MODE } from "./constants.js";

const CAD_WORKSPACE_SESSION_STORAGE_KEY = "cad-explorer:workbench-session:v2";
const CAD_WORKSPACE_LOCAL_STORAGE_KEY = "cad-explorer:workbench-global:v1";
export const LOOK_SETTINGS_STORAGE_KEY = "cad-explorer:look-settings";
const CAD_WORKSPACE_GLASS_TONE_STORAGE_KEY = "cad-explorer:workbench-glass-tone:v1";
const DXF_BEND_OVERRIDE_STORAGE_KEY = "cad-explorer:dxf-bend-overrides:v1";
const CAD_WORKSPACE_SESSION_STORAGE_VERSION = 2;
const CAD_WORKSPACE_LOCAL_STORAGE_VERSION = 1;
const CAD_WORKSPACE_LEGACY_DEFAULT_PANEL_WIDTH = 300;

export const CAD_WORKSPACE_DEFAULT_SIDEBAR_WIDTH = 260;
export const CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH = 260;
export const CAD_WORKSPACE_DEFAULT_GLASS_TONE = DEFAULT_LOOK_PRESET.glassTone === "dark" ? "dark" : "light";

function hasOwn(object, key) {
  return Object.prototype.hasOwnProperty.call(object, key);
}

function normalizeString(value, fallback = "") {
  return String(value ?? fallback);
}

function normalizeStringList(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((entry) => String(entry ?? "").trim())
    .filter(Boolean);
}

function normalizeUniqueStringList(value) {
  return [...new Set(normalizeStringList(value))];
}

function normalizeBoolean(value, fallback) {
  if (typeof value === "boolean") {
    return value;
  }
  return fallback;
}

function normalizeNumber(value, fallback) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function normalizePanelWidth(value, fallback) {
  const numericValue = normalizeNumber(value, fallback);
  return numericValue === CAD_WORKSPACE_LEGACY_DEFAULT_PANEL_WIDTH ? fallback : numericValue;
}

function cloneStringList(value) {
  return Array.isArray(value) ? [...value] : [];
}

function stringListEqual(a, b) {
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

function cloneDrawingPoint(point) {
  return {
    x: Number(point?.x) || 0,
    y: Number(point?.y) || 0
  };
}

function clonePoint3(point) {
  return Array.isArray(point) ? [
    Number(point[0]) || 0,
    Number(point[1]) || 0,
    Number(point[2]) || 0
  ] : null;
}

function clonePoint2(point) {
  return Array.isArray(point) ? [
    Number(point[0]) || 0,
    Number(point[1]) || 0
  ] : null;
}

function normalizeDrawingTool(value) {
  const normalized = normalizeString(value || DRAWING_TOOL.FREEHAND);
  switch (normalized) {
    case DRAWING_TOOL.LINE:
    case DRAWING_TOOL.ARROW:
    case DRAWING_TOOL.DOUBLE_ARROW:
    case DRAWING_TOOL.RECTANGLE:
    case DRAWING_TOOL.CIRCLE:
    case DRAWING_TOOL.FILL:
    case DRAWING_TOOL.ERASE:
    case DRAWING_TOOL.FREEHAND:
      return normalized;
    default:
      return DRAWING_TOOL.FREEHAND;
  }
}

function normalizeTabToolMode(value) {
  const normalized = normalizeString(value || TAB_TOOL_MODE.REFERENCES);
  if (normalized === TAB_TOOL_MODE.DRAW) {
    return TAB_TOOL_MODE.DRAW;
  }
  if (normalized === TAB_TOOL_MODE.MEASURE) {
    return TAB_TOOL_MODE.MEASURE;
  }
  return TAB_TOOL_MODE.REFERENCES;
}

function pointsEqualN(a, b, length) {
  if (a === b) {
    return true;
  }
  if (!Array.isArray(a) || !Array.isArray(b) || a.length < length || b.length < length) {
    return false;
  }
  for (let index = 0; index < length; index += 1) {
    if (a[index] !== b[index]) {
      return false;
    }
  }
  return true;
}

function cloneSurfaceLineData(surfaceLine) {
  if (!surfaceLine || typeof surfaceLine !== "object") {
    return null;
  }
  return {
    referenceId: String(surfaceLine.referenceId || ""),
    selector: String(surfaceLine.selector || ""),
    normalizedSelector: String(surfaceLine.normalizedSelector || ""),
    faceToken: String(surfaceLine.faceToken || ""),
    partId: String(surfaceLine.partId || ""),
    surfaceType: String(surfaceLine.surfaceType || ""),
    startPoint: clonePoint3(surfaceLine.startPoint),
    endPoint: clonePoint3(surfaceLine.endPoint),
    startUv: clonePoint2(surfaceLine.startUv),
    endUv: clonePoint2(surfaceLine.endUv)
  };
}

function surfaceLineEqual(a, b) {
  if (a === b) {
    return true;
  }
  if (!a || !b) {
    return false;
  }
  return (
    a.referenceId === b.referenceId &&
    a.selector === b.selector &&
    a.normalizedSelector === b.normalizedSelector &&
    a.faceToken === b.faceToken &&
    a.partId === b.partId &&
    a.surfaceType === b.surfaceType &&
    pointsEqualN(a.startPoint, b.startPoint, 3) &&
    pointsEqualN(a.endPoint, b.endPoint, 3) &&
    pointsEqualN(a.startUv, b.startUv, 2) &&
    pointsEqualN(a.endUv, b.endUv, 2)
  );
}

function drawingPointsEqual(a, b) {
  if (a === b) {
    return true;
  }
  if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) {
    return false;
  }
  for (let index = 0; index < a.length; index += 1) {
    if (a[index]?.x !== b[index]?.x || a[index]?.y !== b[index]?.y) {
      return false;
    }
  }
  return true;
}

function cloneDrawingStroke(stroke) {
  const rawTool = normalizeString(stroke?.tool || DRAWING_TOOL.FREEHAND);
  if (rawTool === DRAWING_TOOL.SURFACE_LINE) {
    return null;
  }
  return {
    id: String(stroke?.id || ""),
    tool: normalizeDrawingTool(rawTool),
    points: Array.isArray(stroke?.points) ? stroke.points.map(cloneDrawingPoint) : [],
    fillPoints: Array.isArray(stroke?.fillPoints) ? stroke.fillPoints.map(cloneDrawingPoint) : [],
    guessed: stroke?.guessed === true,
    surfaceLine: cloneSurfaceLineData(stroke?.surfaceLine)
  };
}

export function cloneDrawingStrokes(strokes) {
  return Array.isArray(strokes) ? strokes.map(cloneDrawingStroke).filter(Boolean) : [];
}

export function drawingStrokesEqual(a, b) {
  if (a === b) {
    return true;
  }
  if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) {
    return false;
  }
  for (let index = 0; index < a.length; index += 1) {
    if (
      a[index]?.id !== b[index]?.id ||
      a[index]?.tool !== b[index]?.tool ||
      a[index]?.guessed !== b[index]?.guessed ||
      !surfaceLineEqual(a[index]?.surfaceLine, b[index]?.surfaceLine) ||
      !drawingPointsEqual(a[index]?.points, b[index]?.points) ||
      !drawingPointsEqual(a[index]?.fillPoints, b[index]?.fillPoints)
    ) {
      return false;
    }
  }
  return true;
}

function cloneDrawingHistoryStack(stack) {
  return Array.isArray(stack) ? stack.map(cloneDrawingStrokes) : [];
}

function drawingHistoryStackEqual(a, b) {
  if (a === b) {
    return true;
  }
  if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) {
    return false;
  }
  for (let index = 0; index < a.length; index += 1) {
    if (!drawingStrokesEqual(a[index], b[index])) {
      return false;
    }
  }
  return true;
}

const TAB_STATE_SCHEMA = [
  {
    key: "renderFormat",
    defaultValue: RENDER_FORMAT.STEP,
    normalize: (value) => {
      const normalized = normalizeString(value || RENDER_FORMAT.STEP).toLowerCase();
      if (normalized === RENDER_FORMAT.DXF) {
        return RENDER_FORMAT.DXF;
      }
      if (normalized === RENDER_FORMAT.STL) {
        return RENDER_FORMAT.STL;
      }
      if (normalized === RENDER_FORMAT.URDF) {
        return RENDER_FORMAT.URDF;
      }
      return RENDER_FORMAT.STEP;
    }
  },
  {
    key: "dxfThicknessMm",
    defaultValue: 0,
    normalize: (value) => {
      const numericValue = normalizeNumber(value, 0);
      return numericValue > 0 ? numericValue : 0;
    }
  },
  {
    key: "referenceQuery",
    defaultValue: "",
    normalize: normalizeString
  },
  {
    key: "selectedReferenceIds",
    defaultValue: [],
    normalize: normalizeStringList,
    clone: cloneStringList,
    equals: stringListEqual
  },
  {
    key: "selectedPartIds",
    defaultValue: [],
    normalize: normalizeStringList,
    clone: cloneStringList,
    equals: stringListEqual
  },
  {
    key: "expandedAssemblyPartIds",
    defaultValue: [],
    normalize: normalizeStringList,
    clone: cloneStringList,
    equals: stringListEqual
  },
  {
    key: "hiddenPartIds",
    defaultValue: [],
    normalize: normalizeStringList,
    clone: cloneStringList,
    equals: stringListEqual
  },
  {
    key: "perspective",
    defaultValue: null,
    normalize: clonePerspectiveSnapshot,
    clone: clonePerspectiveSnapshot,
    equals: perspectiveSnapshotEqual
  },
  {
    key: "drawingTool",
    defaultValue: DRAWING_TOOL.FREEHAND,
    normalize: normalizeDrawingTool
  },
  {
    key: "tabToolsOpen",
    defaultValue: false,
    normalize: (value) => normalizeBoolean(value, false)
  },
  {
    key: "tabToolMode",
    defaultValue: TAB_TOOL_MODE.REFERENCES,
    normalize: normalizeTabToolMode
  },
  {
    key: "drawingStrokes",
    defaultValue: [],
    normalize: cloneDrawingStrokes,
    clone: cloneDrawingStrokes,
    equals: drawingStrokesEqual
  },
  {
    key: "drawingUndoStack",
    defaultValue: [],
    normalize: cloneDrawingHistoryStack,
    clone: cloneDrawingHistoryStack,
    equals: drawingHistoryStackEqual
  },
  {
    key: "drawingRedoStack",
    defaultValue: [],
    normalize: cloneDrawingHistoryStack,
    clone: cloneDrawingHistoryStack,
    equals: drawingHistoryStackEqual
  }
];

const GLOBAL_STATE_SCHEMA = [
  {
    key: "query",
    defaultValue: "",
    normalize: normalizeString
  },
  {
    key: "expandedDirectoryIds",
    defaultValue: [],
    normalize: normalizeUniqueStringList,
    clone: cloneStringList,
    equals: stringListEqual
  },
  {
    key: "sidebarOpen",
    defaultValue: true,
    normalize: (value) => normalizeBoolean(value, true)
  },
  {
    key: "sidebarWidth",
    defaultValue: CAD_WORKSPACE_DEFAULT_SIDEBAR_WIDTH,
    normalize: (value) => normalizePanelWidth(value, CAD_WORKSPACE_DEFAULT_SIDEBAR_WIDTH)
  },
  {
    key: "tabToolsWidth",
    defaultValue: CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH,
    normalize: (value) => normalizePanelWidth(value, CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH)
  },
  {
    key: "urdfEntryAnimationEnabled",
    defaultValue: true,
    normalize: (value) => normalizeBoolean(value, true)
  }
];

function normalizeSchemaState(schema, source = {}) {
  const normalized = {};
  for (const field of schema) {
    const value = hasOwn(source || {}, field.key) ? source[field.key] : field.defaultValue;
    normalized[field.key] = field.normalize ? field.normalize(value, field.defaultValue) : value;
  }
  return normalized;
}

function cloneSchemaState(schema, source = {}) {
  const normalized = normalizeSchemaState(schema, source);
  const cloned = {};
  for (const field of schema) {
    const value = normalized[field.key];
    cloned[field.key] = field.clone ? field.clone(value) : value;
  }
  return cloned;
}

function schemaStateEqual(schema, a = {}, b = {}) {
  for (const field of schema) {
    const left = hasOwn(a || {}, field.key) ? a[field.key] : field.defaultValue;
    const right = hasOwn(b || {}, field.key) ? b[field.key] : field.defaultValue;
    const equals = field.equals || Object.is;
    if (!equals(left, right)) {
      return false;
    }
  }
  return true;
}

function normalizeTabKey(value) {
  return String(value || "").trim();
}

function keyIsAllowed(key, validEntryKeys) {
  if (!key) {
    return false;
  }
  if (!(validEntryKeys instanceof Set)) {
    return true;
  }
  return validEntryKeys.has(key);
}

function normalizeTabsState(source = {}, validEntryKeys) {
  const seenKeys = new Set();
  const openOrder = [];
  const byKey = {};

  const addTab = (key, tabState) => {
    const normalizedKey = normalizeTabKey(key);
    if (!keyIsAllowed(normalizedKey, validEntryKeys) || seenKeys.has(normalizedKey)) {
      return;
    }
    seenKeys.add(normalizedKey);
    openOrder.push(normalizedKey);
    byKey[normalizedKey] = cloneTabSnapshot(tabState || {});
  };

  const tabsState = source?.tabs && typeof source.tabs === "object"
    ? source.tabs
    : null;
  const tabsOrder = Array.isArray(tabsState?.openOrder) ? tabsState.openOrder : [];
  const tabsByKey = tabsState?.byKey && typeof tabsState.byKey === "object" ? tabsState.byKey : {};

  for (const key of tabsOrder) {
    const normalizedKey = normalizeTabKey(key);
    addTab(normalizedKey, tabsByKey?.[normalizedKey]);
  }
  for (const [key, value] of Object.entries(tabsByKey || {})) {
    addTab(key, value);
  }
  for (const candidate of Array.isArray(source?.openTabs) ? source.openTabs : []) {
    addTab(candidate?.key, candidate || {});
  }

  let selectedKey = normalizeTabKey(
    source?.selectedKey ||
    tabsState?.selectedKey ||
    ""
  );
  if (selectedKey && !seenKeys.has(selectedKey)) {
    if (keyIsAllowed(selectedKey, validEntryKeys)) {
      addTab(selectedKey, {});
    } else {
      selectedKey = "";
    }
  }
  if (!selectedKey || !seenKeys.has(selectedKey)) {
    selectedKey = openOrder[0] || "";
  }

  return {
    openOrder,
    byKey,
    selectedKey
  };
}

function buildOpenTabs(tabsState) {
  return tabsState.openOrder
    .map((key) => ({
      key,
      ...cloneTabSnapshot(tabsState.byKey?.[key] || {})
    }));
}

function normalizeGlobalState(source = {}, localSource = null) {
  const localNormalized = localSource && typeof localSource === "object"
    ? normalizeSchemaState(GLOBAL_STATE_SCHEMA, localSource)
    : null;
  if (!localNormalized) {
    return normalizeSchemaState(GLOBAL_STATE_SCHEMA, source);
  }
  return normalizeSchemaState(GLOBAL_STATE_SCHEMA, {
    ...(source && typeof source === "object" ? source : {}),
    ...localNormalized
  });
}

function parseLocalGlobalState(rawValue) {
  if (!rawValue || typeof rawValue !== "object") {
    return null;
  }
  if (Number(rawValue.version) !== CAD_WORKSPACE_LOCAL_STORAGE_VERSION) {
    return null;
  }
  if (!rawValue.global || typeof rawValue.global !== "object") {
    return null;
  }
  return normalizeSchemaState(GLOBAL_STATE_SCHEMA, rawValue.global);
}

function readStorageJson(storage, key) {
  try {
    const rawValue = storage.getItem(key);
    return rawValue ? JSON.parse(rawValue) : null;
  } catch {
    return null;
  }
}

function reportStorageWriteFailure(key, error, options = {}) {
  if (typeof options.onWriteError === "function") {
    options.onWriteError({ key, error });
  }
}

function writeStorageText(storage, key, value, options = {}) {
  try {
    storage.setItem(key, String(value));
    return true;
  } catch (error) {
    reportStorageWriteFailure(key, error, options);
    return false;
  }
}

function writeStorageJson(storage, key, value, options = {}) {
  try {
    storage.setItem(key, JSON.stringify(value));
    return true;
  } catch (error) {
    reportStorageWriteFailure(key, error, options);
    return false;
  }
}

function removeStorageItem(storage, key, options = {}) {
  try {
    storage.removeItem(key);
    return true;
  } catch (error) {
    reportStorageWriteFailure(key, error, options);
    return false;
  }
}

export function readLookSettings() {
  if (typeof window === "undefined") {
    return cloneLookSettings(DEFAULT_LOOK_SETTINGS);
  }
  try {
    const rawValue = readStorageJson(window.localStorage, LOOK_SETTINGS_STORAGE_KEY);
    return rawValue && typeof rawValue === "object"
      ? normalizeLookSettings(rawValue)
      : cloneLookSettings(DEFAULT_LOOK_SETTINGS);
  } catch (error) {
    console.warn("Failed to parse stored look settings", error);
    return cloneLookSettings(DEFAULT_LOOK_SETTINGS);
  }
}

export function writeLookSettings(lookSettings, options = {}) {
  if (typeof window === "undefined") {
    return true;
  }
  return writeStorageJson(
    window.localStorage,
    LOOK_SETTINGS_STORAGE_KEY,
    normalizeLookSettings(lookSettings),
    options
  );
}

export function normalizeCadWorkspaceGlassTone(value, fallback = CAD_WORKSPACE_DEFAULT_GLASS_TONE) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "dark" || normalized === "light") {
    return normalized;
  }
  return fallback === "light" ? "light" : "dark";
}

export function readCadWorkspaceGlassTone() {
  if (typeof window === "undefined") {
    return CAD_WORKSPACE_DEFAULT_GLASS_TONE;
  }
  return normalizeCadWorkspaceGlassTone(window.localStorage.getItem(CAD_WORKSPACE_GLASS_TONE_STORAGE_KEY));
}

export function writeCadWorkspaceGlassTone(value, options = {}) {
  if (typeof window === "undefined") {
    return true;
  }
  return writeStorageText(
    window.localStorage,
    CAD_WORKSPACE_GLASS_TONE_STORAGE_KEY,
    normalizeCadWorkspaceGlassTone(value),
    options
  );
}

export function writeThemePreference(themeId, options = {}) {
  if (typeof window === "undefined") {
    return true;
  }
  return writeStorageText(window.localStorage, THEME_STORAGE_KEY, themeId, options);
}

function bendStorageKey(index) {
  return `B${index + 1}`;
}

function normalizeStoredDxfBendSetting(value) {
  if (!value || typeof value !== "object") {
    return null;
  }
  return {
    direction: normalizeDxfBendDirection(value.direction),
    angleDeg: normalizeDxfBendAngleDeg(value.angleDeg)
  };
}

function readStoredDxfBendSettings(value) {
  const source = Array.isArray(value?.bendsByIndex)
    ? value.bendsByIndex
    : value?.bendsByIndex && typeof value.bendsByIndex === "object"
      ? value.bendsByIndex
      : Array.isArray(value?.bends)
        ? value.bends
        : value?.bends && typeof value.bends === "object"
          ? value.bends
          : null;

  if (!source) {
    return [];
  }

  if (Array.isArray(source)) {
    return source.map(normalizeStoredDxfBendSetting);
  }

  const bends = [];
  for (const [key, setting] of Object.entries(source)) {
    const match = /^B([1-9]\d*)$/i.exec(key.trim());
    if (!match) {
      continue;
    }
    bends[Number(match[1]) - 1] = normalizeStoredDxfBendSetting(setting);
  }
  return bends;
}

function buildStoredDxfBendSettings(value) {
  const source = Array.isArray(value) ? value : [];
  return Object.fromEntries(
    source.map((setting, index) => [
      bendStorageKey(index),
      {
        direction: normalizeDxfBendDirection(setting?.direction),
        angleDeg: normalizeDxfBendAngleDeg(setting?.angleDeg)
      }
    ])
  );
}

export function dxfBendSettingsEqual(a, b) {
  const left = Array.isArray(a) ? a : [];
  const right = Array.isArray(b) ? b : [];
  if (left.length !== right.length) {
    return false;
  }
  return left.every((setting, index) => (
    normalizeDxfBendDirection(setting?.direction) === normalizeDxfBendDirection(right[index]?.direction) &&
    normalizeDxfBendAngleDeg(setting?.angleDeg) === normalizeDxfBendAngleDeg(right[index]?.angleDeg)
  ));
}

function readDxfBendOverrideMap() {
  if (typeof window === "undefined") {
    return {};
  }
  const rawValue = readStorageJson(window.sessionStorage, DXF_BEND_OVERRIDE_STORAGE_KEY);
  return rawValue && typeof rawValue === "object" ? rawValue : {};
}

export function readDxfBendOverridesForEntry(fileRef) {
  if (!fileRef) {
    return null;
  }
  const settings = readDxfBendOverrideMap()[fileRef];
  if (!settings || typeof settings !== "object") {
    return null;
  }
  return {
    bends: readStoredDxfBendSettings(settings)
  };
}

export function writeDxfBendOverridesForEntry(fileRef, value, options = {}) {
  if (typeof window === "undefined" || !fileRef) {
    return true;
  }
  const nextMap = {
    ...readDxfBendOverrideMap()
  };
  if (value && typeof value === "object") {
    nextMap[fileRef] = {
      bendsByIndex: buildStoredDxfBendSettings(value.bends)
    };
  } else {
    delete nextMap[fileRef];
  }
  if (Object.keys(nextMap).length) {
    return writeStorageJson(window.sessionStorage, DXF_BEND_OVERRIDE_STORAGE_KEY, nextMap, options);
  }
  return removeStorageItem(window.sessionStorage, DXF_BEND_OVERRIDE_STORAGE_KEY, options);
}

export function createTabSnapshot(overrides = {}) {
  return normalizeSchemaState(TAB_STATE_SCHEMA, overrides || {});
}

export function cloneTabSnapshot(snapshot) {
  return cloneSchemaState(TAB_STATE_SCHEMA, snapshot || {});
}

export function tabSnapshotEqual(a, b) {
  return schemaStateEqual(TAB_STATE_SCHEMA, a || {}, b || {});
}

export function createTabRecord(key, overrides = {}) {
  return {
    key: normalizeTabKey(key),
    ...cloneTabSnapshot(overrides)
  };
}

export function buildCadWorkspaceSessionState(source = {}, { validEntryKeys, localGlobalState } = {}) {
  const globalSource = (source?.globalState && typeof source.globalState === "object")
    ? source.globalState
    : (source?.global && typeof source.global === "object")
      ? source.global
      : source;

  const globalState = normalizeGlobalState(globalSource, localGlobalState);
  const tabsState = normalizeTabsState(source, validEntryKeys);
  const openTabs = buildOpenTabs(tabsState);

  return {
    version: CAD_WORKSPACE_SESSION_STORAGE_VERSION,
    globalState,
    tabsState,
    openTabs,
    selectedKey: tabsState.selectedKey,
    query: globalState.query,
    expandedDirectoryIds: globalState.expandedDirectoryIds,
    sidebarOpen: globalState.sidebarOpen,
    sidebarWidth: globalState.sidebarWidth,
    tabToolsWidth: globalState.tabToolsWidth,
    urdfEntryAnimationEnabled: globalState.urdfEntryAnimationEnabled
  };
}

function serializeCadWorkspaceSessionState(snapshot) {
  return {
    version: CAD_WORKSPACE_SESSION_STORAGE_VERSION,
    global: cloneSchemaState(GLOBAL_STATE_SCHEMA, snapshot.globalState),
    tabs: {
      selectedKey: snapshot.tabsState.selectedKey,
      openOrder: cloneStringList(snapshot.tabsState.openOrder),
      byKey: Object.fromEntries(
        Object.entries(snapshot.tabsState.byKey || {}).map(([key, value]) => [key, cloneTabSnapshot(value)])
      )
    }
  };
}

function parseCadWorkspaceSessionState(rawValue, validEntryKeys, localGlobalState) {
  if (!rawValue || typeof rawValue !== "object") {
    return null;
  }

  const version = Number(rawValue.version);
  if (version !== CAD_WORKSPACE_SESSION_STORAGE_VERSION) {
    return null;
  }

  if (!rawValue.tabs || typeof rawValue.tabs !== "object") {
    return null;
  }

  return buildCadWorkspaceSessionState({
    global: rawValue.global,
    tabs: rawValue.tabs
  }, {
    validEntryKeys,
    localGlobalState
  });
}

export function readCadWorkspaceSessionState(validEntryKeys) {
  if (typeof window === "undefined") {
    return null;
  }

  const localGlobalState = parseLocalGlobalState(
    readStorageJson(window.localStorage, CAD_WORKSPACE_LOCAL_STORAGE_KEY)
  );

  const v2Session = parseCadWorkspaceSessionState(
    readStorageJson(window.sessionStorage, CAD_WORKSPACE_SESSION_STORAGE_KEY),
    validEntryKeys,
    localGlobalState
  );
  if (v2Session) {
    return v2Session;
  }

  if (localGlobalState) {
    return buildCadWorkspaceSessionState(
      {
        globalState: localGlobalState,
        openTabs: [],
        selectedKey: ""
      },
      { validEntryKeys }
    );
  }

  return null;
}

export function writeCadWorkspaceSessionState(source, options = {}) {
  if (typeof window === "undefined") {
    return true;
  }

  const snapshot = buildCadWorkspaceSessionState(source);
  const sessionWritten = writeStorageJson(
    window.sessionStorage,
    CAD_WORKSPACE_SESSION_STORAGE_KEY,
    serializeCadWorkspaceSessionState(snapshot),
    options
  );
  const globalWritten = writeStorageJson(
    window.localStorage,
    CAD_WORKSPACE_LOCAL_STORAGE_KEY,
    {
      version: CAD_WORKSPACE_LOCAL_STORAGE_VERSION,
      global: cloneSchemaState(GLOBAL_STATE_SCHEMA, snapshot.globalState)
    },
    options
  );
  return sessionWritten && globalWritten;
}

export function resetCadWorkspacePersistence({ onWriteError } = {}) {
  if (typeof window === "undefined") {
    return true;
  }

  const localKeys = [
    CAD_WORKSPACE_LOCAL_STORAGE_KEY,
    LOOK_SETTINGS_STORAGE_KEY,
    THEME_STORAGE_KEY,
    CAD_WORKSPACE_GLASS_TONE_STORAGE_KEY
  ];
  const sessionKeys = [
    CAD_WORKSPACE_SESSION_STORAGE_KEY,
    DXF_BEND_OVERRIDE_STORAGE_KEY
  ];

  let ok = true;
  for (const key of localKeys) {
    ok = removeStorageItem(window.localStorage, key, { onWriteError }) && ok;
  }
  for (const key of sessionKeys) {
    ok = removeStorageItem(window.sessionStorage, key, { onWriteError }) && ok;
  }
  return ok;
}

export function consumeCadWorkspacePersistenceResetRequest(options = {}) {
  if (typeof window === "undefined") {
    return false;
  }
  const url = new URL(window.location.href);
  if (url.searchParams.get("resetPersistence") !== "1") {
    return false;
  }

  resetCadWorkspacePersistence(options);
  url.searchParams.delete("resetPersistence");
  window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
  return true;
}

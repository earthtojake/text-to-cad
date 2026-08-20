import { clonePerspectiveSnapshot, perspectiveSnapshotEqual } from "cadjs/lib/perspective.js";
import {
  CUSTOM_THEME_ID,
  DEFAULT_THEME_ID,
  DEFAULT_THEME_PRESET,
  getThemePresetIdForSettings,
  inferThemeSettingsSceneTone,
  normalizeThemeId,
  normalizeThemeSettings,
  resolveThemeSettingsForId
} from "cadjs/lib/themeSettings.js";
import { THEME_STORAGE_KEY } from "../ui/colorScheme.js";
import { normalizeRenderFormat } from "cadjs/lib/fileFormats.js";
import { isCadWorkspaceCompactFileSheetViewport } from "./breakpoints.js";
import { DRAWING_TOOL, RENDER_FORMAT, TAB_TOOL_MODE } from "./constants.js";

export { THEME_STORAGE_KEY };
export const THEME_STORAGE_VERSION = 12;

export const CAD_DIRECTORY_SESSION_STORAGE_VERSION = 1;
export const CAD_DIRECTORY_SESSION_STORAGE_KEY = `cad-viewer:directory-session:v${CAD_DIRECTORY_SESSION_STORAGE_VERSION}`;
export const CAD_WORKSPACE_DEFAULT_SIDEBAR_WIDTH = 280;
export const CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH = 365;
export const CAD_WORKSPACE_COMPACT_TAB_TOOLS_WIDTH = 280;
export const CAD_WORKSPACE_DEFAULT_GLASS_TONE = inferThemeSettingsSceneTone(DEFAULT_THEME_PRESET.settings);

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

function normalizeNullableUniqueStringList(value) {
  return Array.isArray(value) ? normalizeUniqueStringList(value) : null;
}

function normalizeNumber(value, fallback) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function normalizeNullablePositiveInteger(value) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue) || numericValue <= 0) {
    return null;
  }
  return Math.round(numericValue);
}

function normalizeBoolean(value, fallback = false) {
  return typeof value === "boolean" ? value : fallback;
}

function normalizeNullableBoolean(value) {
  return typeof value === "boolean" ? value : null;
}

export function fileSheetWidthPxForSessionState(value, defaultWidth = CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH) {
  const normalizedWidth = normalizeNullablePositiveInteger(value);
  const normalizedDefaultWidth = (
    normalizeNullablePositiveInteger(defaultWidth) ||
    normalizeNullablePositiveInteger(CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH)
  );
  if (!normalizedWidth || normalizedWidth === normalizedDefaultWidth) {
    return null;
  }
  return normalizedWidth;
}

export function fileViewerWidthPxForSessionState(value, defaultWidth = CAD_WORKSPACE_DEFAULT_SIDEBAR_WIDTH) {
  const normalizedWidth = normalizeNullablePositiveInteger(value);
  const normalizedDefaultWidth = (
    normalizeNullablePositiveInteger(defaultWidth) ||
    normalizeNullablePositiveInteger(CAD_WORKSPACE_DEFAULT_SIDEBAR_WIDTH)
  );
  if (!normalizedWidth || normalizedWidth === normalizedDefaultWidth) {
    return null;
  }
  return normalizedWidth;
}

export function cadWorkspaceDefaultFileSheetWidthForViewport(width) {
  return isCadWorkspaceCompactFileSheetViewport(width)
    ? CAD_WORKSPACE_COMPACT_TAB_TOOLS_WIDTH
    : CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH;
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

function normalizeTabCameraSnapshot(value) {
  const snapshot = clonePerspectiveSnapshot(value);
  if (!snapshot) {
    return null;
  }
  const zoom = Number(snapshot.zoom);
  return {
    position: snapshot.position,
    target: snapshot.target,
    up: snapshot.up,
    zoom: Number.isFinite(zoom) && zoom > 0 ? zoom : 1
  };
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
  if (
    normalized === TAB_TOOL_MODE.DRAW ||
    normalized === TAB_TOOL_MODE.MEASURE ||
    normalized === TAB_TOOL_MODE.PAN
  ) {
    return normalized;
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
    normalize: (value) => normalizeRenderFormat(value)
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
    key: "inspectedAssemblyNodeId",
    defaultValue: "",
    normalize: (value) => normalizeString(value).trim()
  },
  {
    key: "expandedAssemblyPartIds",
    defaultValue: [],
    normalize: normalizeStringList,
    clone: cloneStringList,
    equals: stringListEqual
  },
  {
    key: "expandedStepTreeNodeIds",
    defaultValue: [],
    normalize: normalizeUniqueStringList,
    clone: cloneStringList,
    equals: stringListEqual
  },
  {
    key: "fileSheetOpenSectionIds",
    defaultValue: null,
    normalize: normalizeNullableUniqueStringList,
    clone: (value) => (Array.isArray(value) ? cloneStringList(value) : null),
    equals: (a, b) => (
      Array.isArray(a) || Array.isArray(b)
        ? stringListEqual(a || [], b || [])
        : a === b
    )
  },
  {
    key: "hiddenPartIds",
    defaultValue: [],
    normalize: normalizeStringList,
    clone: cloneStringList,
    equals: stringListEqual
  },
  {
    key: "camera",
    defaultValue: null,
    normalize: normalizeTabCameraSnapshot,
    clone: normalizeTabCameraSnapshot,
    equals: perspectiveSnapshotEqual
  },
  {
    key: "drawingTool",
    defaultValue: DRAWING_TOOL.FREEHAND,
    normalize: normalizeDrawingTool
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

function normalizeSchemaState(schema, source = {}) {
  const normalized = {};
  for (const field of schema) {
    let value = hasOwn(source || {}, field.key) ? source[field.key] : undefined;
    if (typeof value === "undefined") {
      value = field.defaultValue;
    }
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
    const left = normalizeSchemaState([field], a)[field.key];
    const right = normalizeSchemaState([field], b)[field.key];
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

function browserSessionStorage() {
  return typeof window !== "undefined" ? window.sessionStorage : null;
}

export function createCadDirectorySessionState(overrides = {}, options = {}) {
  return {
    fileViewerOpen: normalizeBoolean(overrides?.fileViewerOpen, false),
    fileViewerExpandedDirectoryIds: normalizeNullableUniqueStringList(overrides?.fileViewerExpandedDirectoryIds),
    fileViewerWidthPx: fileViewerWidthPxForSessionState(
      overrides?.fileViewerWidthPx,
      options.defaultFileViewerWidthPx
    ),
    fileSheetOpen: normalizeNullableBoolean(overrides?.fileSheetOpen),
    fileSheetWidthPx: fileSheetWidthPxForSessionState(
      overrides?.fileSheetWidthPx,
      options.defaultFileSheetWidthPx
    ),
    theme: normalizeDirectorySessionThemeSlice(overrides?.theme)
  };
}

function buildCadDirectorySessionStoragePayload(state = {}, options = {}) {
  const normalizedState = createCadDirectorySessionState(state, options);
  const payload = {
    version: CAD_DIRECTORY_SESSION_STORAGE_VERSION
  };
  if (normalizedState.fileViewerOpen || hasOwn(state || {}, "fileViewerOpen")) {
    payload.fileViewerOpen = normalizedState.fileViewerOpen;
  }
  if (Array.isArray(normalizedState.fileViewerExpandedDirectoryIds)) {
    payload.fileViewerExpandedDirectoryIds = normalizedState.fileViewerExpandedDirectoryIds;
  }
  if (normalizedState.fileViewerWidthPx) {
    payload.fileViewerWidthPx = normalizedState.fileViewerWidthPx;
  }
  if (typeof normalizedState.fileSheetOpen === "boolean") {
    payload.fileSheetOpen = normalizedState.fileSheetOpen;
  }
  if (normalizedState.fileSheetWidthPx) {
    payload.fileSheetWidthPx = normalizedState.fileSheetWidthPx;
  }
  if (normalizedState.theme) {
    payload.theme = normalizedState.theme;
  }
  return Object.keys(payload).length > 1 ? payload : null;
}

export function readCadDirectorySessionState(options = {}) {
  const storage = options.storage || browserSessionStorage();
  if (!storage) {
    return createCadDirectorySessionState({}, options);
  }
  const rawValue = readStorageJson(storage, CAD_DIRECTORY_SESSION_STORAGE_KEY);
  if (!rawValue || rawValue.version !== CAD_DIRECTORY_SESSION_STORAGE_VERSION) {
    return createCadDirectorySessionState({}, options);
  }
  return createCadDirectorySessionState(rawValue, options);
}

export function writeCadDirectorySessionState(state = {}, options = {}) {
  const storage = options.storage || browserSessionStorage();
  if (!storage) {
    return true;
  }
  const payload = buildCadDirectorySessionStoragePayload(state, options);
  if (!payload) {
    return removeStorageItem(storage, CAD_DIRECTORY_SESSION_STORAGE_KEY, options);
  }
  return writeStorageJson(storage, CAD_DIRECTORY_SESSION_STORAGE_KEY, payload, options);
}

// --- one-shot tutorial tips ---------------------------------------------
// Each tip fires the first time its moment happens and never again, so the
// record of which ones have been seen outlives the session. `?resetTips=1`
// clears it (see applyTutorialTipResetQueryParam) for demos and manual testing.
export const TUTORIAL_TIP_STORAGE_VERSION = 1;
export const TUTORIAL_TIP_STORAGE_KEY = `cad-viewer:tutorial-tips:v${TUTORIAL_TIP_STORAGE_VERSION}`;
export const TUTORIAL_TIP_RESET_QUERY_PARAM = "resetTips";

export const TUTORIAL_TIP_IDS = Object.freeze({
  COPY_REFERENCE: "copyReference"
});

function browserLocalStorage() {
  return typeof window !== "undefined" ? window.localStorage : null;
}

export function readSeenTutorialTipIds(options = {}) {
  const storage = options.storage || browserLocalStorage();
  if (!storage) {
    return [];
  }
  const rawValue = readStorageJson(storage, TUTORIAL_TIP_STORAGE_KEY);
  if (!rawValue || rawValue.version !== TUTORIAL_TIP_STORAGE_VERSION) {
    return [];
  }
  return normalizeUniqueStringList(rawValue.seen);
}

export function tutorialTipSeen(tipId, options = {}) {
  const normalizedTipId = String(tipId || "").trim();
  return Boolean(normalizedTipId) && readSeenTutorialTipIds(options).includes(normalizedTipId);
}

export function markTutorialTipSeen(tipId, options = {}) {
  const storage = options.storage || browserLocalStorage();
  const normalizedTipId = String(tipId || "").trim();
  if (!storage || !normalizedTipId) {
    return false;
  }
  const seen = readSeenTutorialTipIds(options);
  if (seen.includes(normalizedTipId)) {
    return true;
  }
  return writeStorageJson(storage, TUTORIAL_TIP_STORAGE_KEY, {
    version: TUTORIAL_TIP_STORAGE_VERSION,
    seen: [...seen, normalizedTipId]
  }, options);
}

export function resetTutorialTips(options = {}) {
  const storage = options.storage || browserLocalStorage();
  if (!storage) {
    return false;
  }
  return removeStorageItem(storage, TUTORIAL_TIP_STORAGE_KEY, options);
}

// Honour `?resetTips=1`, then strip it from the URL so a reload does not keep
// re-arming the tips: the reset is a one-shot action, not a mode.
export function applyTutorialTipResetQueryParam(options = {}) {
  if (typeof window === "undefined") {
    return false;
  }
  let url;
  try {
    url = new URL(window.location.href);
  } catch {
    return false;
  }
  if (!url.searchParams.has(TUTORIAL_TIP_RESET_QUERY_PARAM)) {
    return false;
  }
  resetTutorialTips(options);
  url.searchParams.delete(TUTORIAL_TIP_RESET_QUERY_PARAM);
  try {
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
  } catch {
    // A blocked replaceState only leaves the param in the address bar.
  }
  return true;
}

function readSystemPrefersDark() {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches === true;
  } catch {
    return false;
  }
}

// Theme state is one active id plus, at most, one customized settings blob.
//
// `themeId` is "system", a built-in preset id, or "custom". Presets are
// read-only: editing any setting writes the result into the single custom slot
// and makes "custom" active, and picking a preset again is what resets it. There
// is deliberately no saved-theme library, and no save/restore action.
function createThemeState(themeId = DEFAULT_THEME_ID, custom = null, { prefersDark = false } = {}) {
  const normalizedThemeId = normalizeThemeId(themeId) || DEFAULT_THEME_ID;
  const normalizedCustom = custom ? normalizeThemeSettings(custom) : null;
  return {
    themeId: normalizedThemeId === CUSTOM_THEME_ID && !normalizedCustom
      ? DEFAULT_THEME_ID
      : normalizedThemeId,
    custom: normalizedCustom,
    settings: resolveThemeSettingsForId(normalizedThemeId, {
      custom: normalizedCustom,
      prefersDark
    })
  };
}

function prefersDarkColorScheme() {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches === true;
  } catch {
    return false;
  }
}

function readThemeStoragePayload() {
  if (typeof window === "undefined") {
    return null;
  }
  const rawValue = readStorageJson(window.localStorage, THEME_STORAGE_KEY);
  return rawValue?.version === THEME_STORAGE_VERSION ? rawValue : null;
}

export function parseThemeSettingsStateFromStorage(rawValue, options = {}) {
  const payload = rawValue?.version === THEME_STORAGE_VERSION ? rawValue : null;
  return createThemeState(payload?.themeId, payload?.custom, options);
}

export function parseThemeSettingsFromStorage(rawValue) {
  return parseThemeSettingsStateFromStorage(rawValue).settings;
}

export function readThemeSettingsState(options = {}) {
  const payload = readThemeStoragePayload();
  return createThemeState(payload?.themeId, payload?.custom, {
    prefersDark: options.prefersDark ?? prefersDarkColorScheme()
  });
}

export function readThemeSettings() {
  return readThemeSettingsState().settings;
}

// Select a theme. Presets and "system" clear nothing — the custom slot is kept so
// the user can flip back to it — but they do become the active, rendered theme.
export function writeThemeState(themeId, options = {}) {
  if (typeof window === "undefined") {
    return true;
  }
  const payload = readThemeStoragePayload();
  const custom = payload?.custom ? normalizeThemeSettings(payload.custom) : null;
  // "custom" with nothing in the slot is not a selectable theme; fall back first
  // so the cleared-storage check below sees the id that will actually be stored.
  const requestedThemeId = normalizeThemeId(themeId) || DEFAULT_THEME_ID;
  const normalizedThemeId = requestedThemeId === CUSTOM_THEME_ID && !custom
    ? DEFAULT_THEME_ID
    : requestedThemeId;
  if (normalizedThemeId === DEFAULT_THEME_ID && !custom) {
    return removeStorageItem(window.localStorage, THEME_STORAGE_KEY, options);
  }
  return writeStorageJson(window.localStorage, THEME_STORAGE_KEY, {
    version: THEME_STORAGE_VERSION,
    themeId: normalizedThemeId,
    custom
  }, options);
}

// Any settings edit lands in the custom slot and activates it, overwriting
// whatever was there: there is only ever one custom theme.
export function writeThemeSettings(themeSettings, options = {}) {
  if (typeof window === "undefined") {
    return true;
  }
  const settings = normalizeThemeSettings(themeSettings);
  const matchingPresetId = getThemePresetIdForSettings(settings);
  if (matchingPresetId) {
    // Edited back to a preset exactly — record the preset, not a custom copy.
    return writeStorageJson(window.localStorage, THEME_STORAGE_KEY, {
      version: THEME_STORAGE_VERSION,
      themeId: matchingPresetId,
      custom: readThemeStoragePayload()?.custom || null
    }, options);
  }
  return writeStorageJson(window.localStorage, THEME_STORAGE_KEY, {
    version: THEME_STORAGE_VERSION,
    themeId: CUSTOM_THEME_ID,
    custom: settings
  }, options);
}


function isPlainStorageObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

// A directory may pin its own theme, overriding the global one for that folder.
// Same shape as global theme state: an id plus the custom slot it may point at.
function normalizeDirectorySessionThemeSlice(value) {
  if (!isPlainStorageObject(value)) {
    return null;
  }
  const themeId = normalizeThemeId(value.themeId);
  if (!themeId) {
    return null;
  }
  const custom = isPlainStorageObject(value.custom) ? normalizeThemeSettings(value.custom) : null;
  if (themeId === CUSTOM_THEME_ID && !custom) {
    return null;
  }
  return { themeId, custom };
}

export function createDirectorySessionThemeSlice(themeState = {}) {
  const slice = normalizeDirectorySessionThemeSlice(themeState);
  if (!slice) {
    return null;
  }
  // Only store a slice that actually overrides something. Persisting one that
  // merely restates the global theme would later shadow a global theme change.
  const globalPayload = readThemeStoragePayload();
  const globalThemeId = normalizeThemeId(globalPayload?.themeId) || DEFAULT_THEME_ID;
  const globalCustom = globalPayload?.custom ? normalizeThemeSettings(globalPayload.custom) : null;
  if (
    slice.themeId === globalThemeId &&
    JSON.stringify(slice.custom) === JSON.stringify(globalCustom)
  ) {
    return null;
  }
  return slice;
}

export function isDirectorySessionThemeSlice(themeSlice) {
  return normalizeDirectorySessionThemeSlice(themeSlice) !== null;
}

export function readDirectoryThemeSettingsState(options = {}) {
  const resolveOptions = {
    prefersDark: options.prefersDark ?? prefersDarkColorScheme()
  };
  const sessionTheme = normalizeDirectorySessionThemeSlice(readCadDirectorySessionState(options).theme);
  if (!sessionTheme) {
    return readThemeSettingsState(resolveOptions);
  }
  return createThemeState(sessionTheme.themeId, sessionTheme.custom, resolveOptions);
}


export function normalizeCadWorkspaceGlassTone(value, fallback = CAD_WORKSPACE_DEFAULT_GLASS_TONE) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "dark" || normalized === "light") {
    return normalized;
  }
  return fallback === "light" ? "light" : "dark";
}

export function readCadWorkspaceGlassTone() {
  return CAD_WORKSPACE_DEFAULT_GLASS_TONE;
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
  const snapshot = cloneTabSnapshot(overrides);
  if (!snapshot.inspectedAssemblyNodeId && Array.isArray(overrides?.expandedAssemblyPartIds)) {
    snapshot.inspectedAssemblyNodeId = String(
      overrides.expandedAssemblyPartIds[overrides.expandedAssemblyPartIds.length - 1] || ""
    ).trim();
  }
  return {
    key: normalizeTabKey(key),
    ...snapshot
  };
}

import { clonePerspectiveSnapshot, perspectiveSnapshotEqual } from "cadjs/lib/perspective.js";
import {
  cloneThemePresetSettings,
  DEFAULT_THEME_PRESET,
  DEFAULT_THEME_PRESET_ID,
  getThemePresetById,
  inferThemeSettingsSceneTone,
  THEME_PRESETS,
  normalizeThemePresetId,
  normalizeThemeSettings
} from "cadjs/lib/themeSettings.js";
import { THEME_STORAGE_KEY } from "../ui/colorScheme.js";
import { normalizeRenderFormat } from "cadjs/lib/fileFormats.js";
import { isCadWorkspaceCompactFileSheetViewport } from "./breakpoints.js";
import { DRAWING_TOOL, RENDER_FORMAT, TAB_TOOL_MODE } from "./constants.js";

export { THEME_STORAGE_KEY };
const THEME_STORAGE_VERSION = 11;
const CUSTOM_THEME_PRESET_ID_PREFIX = "custom:";
export const THEME_APPEARANCE_QUERY_PARAM = "appearance";

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
  return normalized === TAB_TOOL_MODE.DRAW ? TAB_TOOL_MODE.DRAW : TAB_TOOL_MODE.REFERENCES;
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
    key: "stepTreeRootShowMore",
    defaultValue: false,
    normalize: normalizeBoolean
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

function normalizeThemeLibraryId(value) {
  return String(value || "").trim();
}

function normalizeThemeLibraryThemeId(value, themes = []) {
  const normalizedThemeId = normalizeThemeLibraryId(value);
  return normalizedThemeId && themes.some((theme) => theme.id === normalizedThemeId)
    ? normalizedThemeId
    : "";
}

function slugifyCustomThemePresetName(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    || "theme";
}

function normalizeThemeLibraryLabel(value) {
  return String(value || "").trim().replace(/\s+/g, " ");
}

function createCustomThemePresetId(label) {
  return `${CUSTOM_THEME_PRESET_ID_PREFIX}${slugifyCustomThemePresetName(label)}`;
}

function createUniqueThemePresetId(label, themes = []) {
  const baseId = createCustomThemePresetId(label);
  const existingIds = new Set(themes.map((theme) => theme.id));
  if (!existingIds.has(baseId)) {
    return baseId;
  }
  for (let index = 2; index < 1000; index += 1) {
    const nextId = `${baseId}-${index}`;
    if (!existingIds.has(nextId)) {
      return nextId;
    }
  }
  return `${baseId}-${Date.now().toString(36)}`;
}

function backgroundPreviewForThemeSettings(settings) {
  const background = settings?.background || {};
  const type = String(background.type || "").trim().toLowerCase();
  if (type === "radial") {
    return `radial-gradient(circle at 32% 24%, ${background.radialInner || background.solidColor || "#111827"} 0%, ${background.radialOuter || background.solidColor || "#030712"} 100%)`;
  }
  if (type === "linear") {
    return `linear-gradient(135deg, ${background.linearStart || background.solidColor || "#111827"} 0%, ${background.solidColor || background.linearStart || "#111827"} 52%, ${background.linearEnd || background.solidColor || "#030712"} 100%)`;
  }
  const color = background.solidColor || settings?.floor?.color || "#111827";
  return `linear-gradient(135deg, ${color} 0%, ${color} 100%)`;
}

function createCustomThemePresetPreview(settings) {
  const modelColor = settings?.materials?.fillColors?.[0] ||
    settings?.materials?.defaultColor ||
    DEFAULT_THEME_PRESET.settings.materials.defaultColor;
  return {
    background: backgroundPreviewForThemeSettings(settings),
    modelColor,
    accentColor: settings?.floor?.color || modelColor || DEFAULT_THEME_PRESET.settings.floor.color
  };
}

function createThemeRecordFromPreset(preset) {
  const settings = normalizeThemeSettings(preset?.settings);
  return {
    id: normalizeThemeLibraryId(preset?.id),
    label: normalizeThemeLibraryLabel(preset?.label) || normalizeThemeLibraryId(preset?.id),
    description: String(preset?.description || "Built-in theme"),
    presetId: normalizeThemePresetId(preset?.id),
    preview: preset?.preview || createCustomThemePresetPreview(settings),
    settings
  };
}

function createDefaultThemeLibrary() {
  return THEME_PRESETS
    .map(createThemeRecordFromPreset)
    .filter((theme) => theme.id && theme.label);
}

function isCustomThemePresetId(value) {
  return normalizeThemeLibraryId(value).startsWith(CUSTOM_THEME_PRESET_ID_PREFIX);
}

function normalizeCustomThemeLibraryThemeId(value, themes = []) {
  const normalizedThemeId = normalizeThemeLibraryId(value);
  return isCustomThemePresetId(normalizedThemeId) && themes.some((theme) => theme.id === normalizedThemeId)
    ? normalizedThemeId
    : "";
}

function normalizeStoredCustomThemePreset(value) {
  const rawId = normalizeThemeLibraryId(value?.id);
  const builtInId = normalizeThemePresetId(rawId);
  if (rawId && builtInId) {
    return null;
  }
  const rawPresetId = normalizeThemeLibraryId(value?.presetId || value?.sourcePresetId);
  const fallbackPresetId = normalizeThemePresetId(rawPresetId);
  if (rawPresetId && !fallbackPresetId) {
    return null;
  }
  const fallbackPreset = fallbackPresetId ? getThemePresetById(fallbackPresetId) : null;
  const id = rawId || createCustomThemePresetId(value?.label || value?.name);
  const label = normalizeThemeLibraryLabel(value?.label || value?.name || fallbackPreset?.label || id);
  const rawTheme = value?.theme && typeof value.theme === "object" ? value.theme : value?.settings;
  const settings = normalizeThemeSettings(
    rawTheme && typeof rawTheme === "object"
      ? rawTheme
      : fallbackPreset?.settings
  );
  if (!id || !label || !settings || normalizeThemePresetId(id)) {
    return null;
  }
  const presetId = fallbackPresetId || "";
  return {
    id,
    label,
    description: String(value?.description || "Saved theme"),
    presetId,
    preview: createCustomThemePresetPreview(settings),
    settings
  };
}

function normalizeStoredCustomThemePresets(rawValue) {
  const values = Array.isArray(rawValue) ? rawValue : rawValue?.themes;
  if (!Array.isArray(values)) {
    return [];
  }
  const seenIds = new Set();
  const themes = [];
  for (const value of values) {
    const theme = normalizeStoredCustomThemePreset(value);
    if (!theme || seenIds.has(theme.id)) {
      continue;
    }
    seenIds.add(theme.id);
    themes.push(theme);
  }
  return themes;
}

function normalizeThemeLibraryPayload(rawValue, options = {}) {
  const fallbackToDefault = options.fallbackToDefault !== false;
  const defaultThemes = fallbackToDefault ? createDefaultThemeLibrary() : [];
  return [
    ...defaultThemes,
    ...normalizeStoredCustomThemePresets(rawValue)
  ];
}

function storedThemePresetPayload(preset) {
  return {
    id: preset.id,
    label: preset.label,
    description: preset.description,
    presetId: preset.presetId || "",
    theme: preset.settings
  };
}

function settingsSignature(settings) {
  return JSON.stringify(normalizeThemeSettings(settings));
}

function resolveDefaultActiveThemeId(themes = createDefaultThemeLibrary()) {
  return normalizeThemeLibraryThemeId(DEFAULT_THEME_PRESET_ID, themes) || themes[0]?.id || DEFAULT_THEME_PRESET_ID;
}

function buildThemeStoragePayload({ activeThemeId = "", themeId = "", customPresets = [], themes = null } = {}) {
  const themeLibrary = normalizeThemeLibraryPayload(themes || customPresets);
  const customThemes = normalizeStoredCustomThemePresets(themeLibrary);
  const normalizedThemeId = normalizeThemeLibraryThemeId(activeThemeId || themeId, themeLibrary);
  const defaultThemeId = resolveDefaultActiveThemeId(themeLibrary);
  if (!customThemes.length && (!normalizedThemeId || normalizedThemeId === defaultThemeId)) {
    return null;
  }
  return {
    version: THEME_STORAGE_VERSION,
    activeThemeId: normalizedThemeId === defaultThemeId ? "" : normalizedThemeId,
    themes: customThemes.map(storedThemePresetPayload)
  };
}

function readThemeStorageState() {
  const defaultThemes = createDefaultThemeLibrary();
  if (typeof window === "undefined") {
    return {
      customPresets: defaultThemes,
      themeId: resolveDefaultActiveThemeId(defaultThemes)
    };
  }
  const rawValue = readStorageJson(window.localStorage, THEME_STORAGE_KEY);
  if (!rawValue || rawValue.version !== THEME_STORAGE_VERSION) {
    return {
      customPresets: defaultThemes,
      themeId: resolveDefaultActiveThemeId(defaultThemes)
    };
  }
  const customPresets = normalizeThemeLibraryPayload(rawValue);
  return {
    customPresets,
    themeId: normalizeThemeLibraryThemeId(rawValue.activeThemeId, customPresets) ||
      resolveDefaultActiveThemeId(customPresets)
  };
}

function writeThemeStorageState(state = {}, options = {}) {
  if (typeof window === "undefined") {
    return true;
  }
  const payload = buildThemeStoragePayload(state);
  if (!payload) {
    return removeStorageItem(window.localStorage, THEME_STORAGE_KEY, options);
  }
  return writeStorageJson(window.localStorage, THEME_STORAGE_KEY, payload, options);
}

export function readCustomThemePresets() {
  return readThemeStorageState().customPresets;
}

export function writeCustomThemePresets(customPresets, options = {}) {
  const currentThemeState = readThemeStorageState();
  const presets = normalizeThemeLibraryPayload(customPresets);
  return writeThemeStorageState({
    themeId: currentThemeState.themeId,
    customPresets: presets
  }, options);
}

export function writeCustomThemePresetLibrary(customPresets, options = {}) {
  const presets = normalizeThemeLibraryPayload(customPresets);
  return writeThemeStorageState({
    themeId: "",
    customPresets: presets
  }, options);
}

function createCustomThemePresetRecord(label, themeSettings, existingPresets, options = {}) {
  const normalizedLabel = normalizeThemeLibraryLabel(label);
  if (!normalizedLabel) {
    return null;
  }
  const settings = normalizeThemeSettings(themeSettings);
  const sourceTheme = getAvailableThemePresetById(options.sourceThemeId || options.presetId, existingPresets);
  return normalizeStoredCustomThemePreset({
    id: createUniqueThemePresetId(normalizedLabel, existingPresets),
    label: normalizedLabel,
    presetId: normalizeThemePresetId(options.sourcePresetId || sourceTheme?.presetId || sourceTheme?.id),
    settings
  });
}

export function saveCustomThemePreset(label, themeSettings, options = {}) {
  const existingPresets = normalizeThemeLibraryPayload(options.customPresets || readCustomThemePresets());
  const preset = createCustomThemePresetRecord(label, themeSettings, existingPresets, options);
  if (!preset) {
    return null;
  }
  const nextPresets = [
    ...existingPresets,
    preset
  ];
  if (!writeCustomThemePresets(nextPresets, options)) {
    return null;
  }
  return preset;
}

export function saveAndActivateCustomThemePreset(label, themeSettings, options = {}) {
  const existingPresets = normalizeThemeLibraryPayload(options.customPresets || readCustomThemePresets());
  const preset = createCustomThemePresetRecord(label, themeSettings, existingPresets, options);
  if (!preset) {
    return null;
  }
  const customPresets = [
    ...existingPresets,
    preset
  ];
  if (!writeThemeStorageState({
    activeThemeId: preset.id,
    customPresets
  }, options)) {
    return null;
  }
  return {
    preset,
    customPresets
  };
}

export function deleteCustomThemePreset(presetId, options = {}) {
  const currentThemeState = readThemeStorageState();
  const existingPresets = normalizeStoredCustomThemePresets(currentThemeState.customPresets);
  const normalizedPresetId = normalizeCustomThemeLibraryThemeId(presetId, existingPresets);
  if (!normalizedPresetId) {
    return false;
  }
  const nextPresets = existingPresets.filter((preset) => preset.id !== normalizedPresetId);
  if (nextPresets.length === existingPresets.length) {
    return true;
  }
  const nextThemeId = currentThemeState.themeId === normalizedPresetId
    ? ""
    : currentThemeState.themeId;
  return writeThemeStorageState({
    themeId: nextThemeId,
    customPresets: nextPresets
  }, options);
}

export function updateThemePresetSettings(presetId, themeSettings, options = {}) {
  const currentThemeState = readThemeStorageState();
  const existingPresets = normalizeStoredCustomThemePresets(currentThemeState.customPresets);
  const normalizedPresetId = normalizeCustomThemeLibraryThemeId(presetId, existingPresets);
  if (!normalizedPresetId) {
    return false;
  }
  const settings = normalizeThemeSettings(themeSettings);
  const nextPresets = existingPresets.map((preset) => (
    preset.id === normalizedPresetId
      ? {
          ...preset,
          preview: createCustomThemePresetPreview(settings),
          settings
        }
      : preset
  ));
  return writeThemeStorageState({
    themeId: normalizedPresetId,
    customPresets: nextPresets
  }, options);
}

export function resetThemePresetToDefault(presetId, options = {}) {
  const currentThemeState = readThemeStorageState();
  const existingPresets = normalizeStoredCustomThemePresets(currentThemeState.customPresets);
  const normalizedPresetId = normalizeCustomThemeLibraryThemeId(presetId, existingPresets);
  const theme = existingPresets.find((candidate) => candidate.id === normalizedPresetId);
  const sourcePresetId = normalizeThemePresetId(theme?.presetId || theme?.id);
  if (!theme || !sourcePresetId) {
    return false;
  }
  const presetRecord = createThemeRecordFromPreset(getThemePresetById(sourcePresetId));
  const nextTheme = {
    ...theme,
    presetId: sourcePresetId,
    preview: createCustomThemePresetPreview(presetRecord.settings),
    settings: presetRecord.settings
  };
  const nextPresets = existingPresets.map((candidate) => (
    candidate.id === normalizedPresetId ? nextTheme : candidate
  ));
  return writeThemeStorageState({
    themeId: currentThemeState.themeId,
    customPresets: nextPresets
  }, options);
}

export function restoreDefaultThemePresets(options = {}) {
  if (typeof window === "undefined") {
    return true;
  }
  return removeStorageItem(window.localStorage, THEME_STORAGE_KEY, options);
}

export function buildAvailableThemePresets(customPresets = readCustomThemePresets()) {
  return normalizeThemeLibraryPayload(customPresets);
}

export function getAvailableThemePresetById(presetId, customPresets = readCustomThemePresets()) {
  const normalizedCustomPresets = normalizeThemeLibraryPayload(customPresets);
  const normalizedPresetId = normalizeThemeLibraryThemeId(presetId, normalizedCustomPresets);
  return buildAvailableThemePresets(customPresets).find((preset) => preset.id === normalizedPresetId) || null;
}

export function cloneAvailableThemePresetSettings(presetId, customPresets = readCustomThemePresets()) {
  const preset = getAvailableThemePresetById(presetId, customPresets);
  return normalizeThemeSettings(preset?.settings || cloneThemePresetSettings(presetId));
}

export function getAvailableThemePresetIdForSettings(themeSettings, customPresets = readCustomThemePresets()) {
  const normalizedSettings = normalizeThemeSettings(themeSettings);
  const normalizedSignature = JSON.stringify(normalizedSettings);
  for (const preset of normalizeThemeLibraryPayload(customPresets)) {
    if (JSON.stringify(normalizeThemeSettings(preset.settings)) === normalizedSignature) {
      return preset.id;
    }
  }
  return null;
}

function cloneThemeSettingsState(
  presetId = "",
  settings = null,
  customPresets = readCustomThemePresets()
) {
  const themes = normalizeThemeLibraryPayload(customPresets);
  const normalizedPresetId = normalizeThemeLibraryThemeId(
    presetId || resolveDefaultActiveThemeId(themes),
    themes
  ) || themes[0]?.id || DEFAULT_THEME_PRESET_ID;
  return {
    presetId: normalizedPresetId,
    settings: normalizeThemeSettings(settings || cloneAvailableThemePresetSettings(normalizedPresetId, customPresets))
  };
}

export function readThemeSettingsStateFromAppearanceQuery(customPresets = readCustomThemePresets()) {
  if (typeof window === "undefined") {
    return null;
  }
  const search = String(window.location?.search || "").trim();
  if (!search) {
    return null;
  }
  let params;
  try {
    params = new URLSearchParams(search);
  } catch {
    return null;
  }
  const requestedPresetId = String(params.get(THEME_APPEARANCE_QUERY_PARAM) || "").trim();
  if (!requestedPresetId) {
    return null;
  }
  const presets = normalizeThemeLibraryPayload(customPresets);
  const normalizedPresetId = normalizeThemeLibraryThemeId(requestedPresetId, presets);
  return normalizedPresetId ? cloneThemeSettingsState(normalizedPresetId, null, presets) : null;
}

function isPlainStorageObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeDirectorySessionThemeSlice(value) {
  if (!isPlainStorageObject(value) || !isPlainStorageObject(value.settings)) {
    return null;
  }
  const settings = normalizeThemeSettings(value.settings);
  if (!settings) {
    return null;
  }
  return {
    presetId: normalizeThemeLibraryId(value.presetId),
    settings
  };
}

export function createDirectorySessionThemeSlice(themeState = {}, customPresets = readCustomThemePresets()) {
  if (!isPlainStorageObject(themeState) || !isPlainStorageObject(themeState.settings)) {
    return null;
  }
  const themes = normalizeThemeLibraryPayload(customPresets);
  const settings = normalizeThemeSettings(themeState.settings);
  const presetId = normalizeThemeLibraryThemeId(themeState.presetId, themes) ||
    getAvailableThemePresetIdForSettings(settings, themes) ||
    resolveDefaultActiveThemeId(themes);
  const savedPreset = getAvailableThemePresetById(presetId, themes);
  if (savedPreset && settingsSignature(settings) === settingsSignature(savedPreset.settings)) {
    return null;
  }
  return {
    presetId,
    settings
  };
}

export function isDirectorySessionThemeSlice(themeSlice) {
  return normalizeDirectorySessionThemeSlice(themeSlice) !== null;
}

export function readDirectoryThemeSettingsState(customPresets = readCustomThemePresets()) {
  const queryState = readThemeSettingsStateFromAppearanceQuery(customPresets);
  if (queryState) {
    return queryState;
  }
  const globalThemeState = readThemeSettingsState(customPresets);
  const sessionTheme = readCadDirectorySessionState({ customPresets }).theme;
  if (!isDirectorySessionThemeSlice(sessionTheme)) {
    return globalThemeState;
  }
  const themes = normalizeThemeLibraryPayload(customPresets);
  const presetId = normalizeThemeLibraryThemeId(sessionTheme.presetId, themes) ||
    globalThemeState.presetId;
  return {
    presetId,
    settings: normalizeThemeSettings(sessionTheme.settings)
  };
}

export function serializeThemeSettingsForStorage(themeSettings, options = {}) {
  const customPresets = normalizeThemeLibraryPayload(options.themes || options.customPresets || readCustomThemePresets());
  const presetId = normalizeThemeLibraryThemeId(
    options.presetId || getAvailableThemePresetIdForSettings(themeSettings, customPresets),
    customPresets
  ) || resolveDefaultActiveThemeId(customPresets);
  return buildThemeStoragePayload({
    themeId: presetId,
    customPresets
  });
}

function storageValuesEqual(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

export function parseThemeSettingsStateFromStorage(rawValue, customPresets = null) {
  const presets = rawValue?.version === THEME_STORAGE_VERSION
    ? normalizeThemeLibraryPayload(rawValue)
    : normalizeThemeLibraryPayload(customPresets);
  const storedPresetId = rawValue?.version === THEME_STORAGE_VERSION
    ? normalizeThemeLibraryThemeId(rawValue.activeThemeId, presets)
    : "";
  return cloneThemeSettingsState(storedPresetId, null, presets);
}

export function parseThemeSettingsFromStorage(rawValue) {
  return parseThemeSettingsStateFromStorage(rawValue).settings;
}

export function readThemeSettingsState(customPresets = readCustomThemePresets()) {
  const queryState = readThemeSettingsStateFromAppearanceQuery(customPresets);
  if (queryState) {
    return queryState;
  }
  if (typeof window === "undefined") {
    return cloneThemeSettingsState("", null, customPresets);
  }
  const storageState = readThemeStorageState();
  const presets = customPresets ? normalizeThemeLibraryPayload(customPresets) : storageState.customPresets;
  const storedPresetId = normalizeThemeLibraryThemeId(storageState.themeId, presets);
  return cloneThemeSettingsState(storedPresetId, null, presets);
}

export function readThemeSettings() {
  return readThemeSettingsState().settings;
}

export function writeThemeSettings(themeSettings, options = {}) {
  if (typeof window === "undefined") {
    return true;
  }
  const serialized = serializeThemeSettingsForStorage(themeSettings, options);
  if (!serialized) {
    return removeStorageItem(window.localStorage, THEME_STORAGE_KEY, options);
  }
  return writeStorageJson(window.localStorage, THEME_STORAGE_KEY, serialized, options);
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

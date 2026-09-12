import { clonePerspectiveSnapshot, perspectiveSnapshotEqual } from "@hardcore/core/lib/perspective.js";
import {
  CUSTOM_THEME_ID,
  DEFAULT_THEME_ID,
  getThemePresetIdForSettings,
  normalizeThemeId,
  normalizeThemeSettings,
  resolveThemeSettingsForId
} from "@hardcore/core/lib/themeSettings.js";
import { normalizeRenderFormat } from "@hardcore/core/lib/fileFormats.js";
import { isCadWorkspaceCompactFileSheetViewport } from "./breakpoints.js";
import { DRAWING_TOOL, RENDER_FORMAT, TAB_TOOL_MODE } from "./constants.js";

export const THEME_STORAGE_VERSION = 13;

export const CAD_DIRECTORY_SESSION_STORAGE_VERSION = 1;
export const CAD_DIRECTORY_SESSION_STORAGE_KEY = `cad-viewer:directory-session:v${CAD_DIRECTORY_SESSION_STORAGE_VERSION}`;
export const CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH = 365;
export const CAD_WORKSPACE_COMPACT_TAB_TOOLS_WIDTH = 280;

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

export function createThemeState(themeId = DEFAULT_THEME_ID, custom = null, { prefersDark = false } = {}) {
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

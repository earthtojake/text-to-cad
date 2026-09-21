import { clonePerspectiveSnapshot, perspectiveSnapshotEqual } from "@hardcore/core/lib/perspective.js";
import { normalizeRenderFormat } from "@hardcore/core/lib/fileFormats.js";
import { isCadWorkspaceCompactFileSheetViewport } from "./breakpoints.js";
import { CAD_TOOL_MODES, RENDER_FORMAT, TAB_TOOL_MODE } from "./constants.js";

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

// A tab's recorded tool mode. Draw is a live mode only: its sketch exists in
// the mounted drawing editor and is discarded with it, so a record never holds
// Draw. A restored tab would otherwise come back with the camera locked under
// an empty sketch.
function normalizeTabToolMode(value) {
  return CAD_TOOL_MODES.persisted(value);
}

// Nothing here restores into Pose: a STEP with kinematics offers the tool, and
// opens in Select.
function tabToolModeForFile(recorded) {
  return CAD_TOOL_MODES.restore(recorded, { never: [TAB_TOOL_MODE.POSE] });
}

const TAB_STATE_SCHEMA = [
  {
    key: "renderFormat",
    defaultValue: RENDER_FORMAT.STEP,
    normalize: (value) => normalizeRenderFormat(value)
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
    key: "tabToolMode",
    defaultValue: TAB_TOOL_MODE.REFERENCES,
    normalize: normalizeTabToolMode
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
    ...snapshot,
    tabToolMode: tabToolModeForFile(overrides?.tabToolMode)
  };
}

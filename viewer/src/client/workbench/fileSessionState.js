import {
  displaySettingsEqual,
  normalizeDisplaySettings
} from "cadjs/lib/displaySettings.js";
import {
  entryAssetHash,
  entryUrdfAssetHash
} from "cadjs/lib/entryAssets.js";
import {
  cloneTabSnapshot,
  tabSnapshotEqual
} from "./persistence.js";

export const FILE_SESSION_STORAGE_VERSION = 1;
export const FILE_SESSION_STORAGE_KEY_PREFIX = "cad-viewer:file-session";
const FILE_SESSION_INDEX_KEY_PREFIX = "cad-viewer:file-session:index";
const DEFAULT_FILE_SESSION_NAMESPACE = "__root__";

function hasOwn(object, key) {
  return Object.prototype.hasOwnProperty.call(object, key);
}

function normalizeString(value, fallback = "") {
  return String(value ?? fallback).trim();
}

function normalizeNumber(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function normalizePositiveNumber(value, fallback = 0) {
  const numericValue = normalizeNumber(value, fallback);
  return numericValue > 0 ? numericValue : fallback;
}

function normalizeBoolean(value, fallback = false) {
  return typeof value === "boolean" ? value : fallback;
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function storageValuesEqual(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

function cloneSerializable(value) {
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value === "string" || typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : 0;
  }
  if (Array.isArray(value)) {
    return value.map(cloneSerializable);
  }
  if (!isPlainObject(value)) {
    return null;
  }
  const cloned = {};
  for (const [key, childValue] of Object.entries(value)) {
    cloned[String(key)] = cloneSerializable(childValue);
  }
  return cloned;
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

export function normalizeFileSessionNamespace(value) {
  return normalizeString(value) || DEFAULT_FILE_SESSION_NAMESPACE;
}

function encodeStoragePart(value) {
  return encodeURIComponent(normalizeString(value));
}

export function fileSessionStorageKey(namespace, fileKey) {
  return [
    FILE_SESSION_STORAGE_KEY_PREFIX,
    `v${FILE_SESSION_STORAGE_VERSION}`,
    encodeStoragePart(normalizeFileSessionNamespace(namespace)),
    encodeStoragePart(fileKey)
  ].join(":");
}

export function fileSessionIndexStorageKey(namespace) {
  return [
    FILE_SESSION_INDEX_KEY_PREFIX,
    `v${FILE_SESSION_STORAGE_VERSION}`,
    encodeStoragePart(normalizeFileSessionNamespace(namespace))
  ].join(":");
}

function readIndex(storage, namespace) {
  const rawValue = readStorageJson(storage, fileSessionIndexStorageKey(namespace));
  if (!rawValue || rawValue.version !== FILE_SESSION_STORAGE_VERSION || !Array.isArray(rawValue.files)) {
    return [];
  }
  return [...new Set(rawValue.files.map((file) => normalizeString(file)).filter(Boolean))];
}

function writeIndex(storage, namespace, files, options = {}) {
  const normalizedFiles = [...new Set(
    (Array.isArray(files) ? files : []).map((file) => normalizeString(file)).filter(Boolean)
  )].sort();
  const key = fileSessionIndexStorageKey(namespace);
  if (!normalizedFiles.length) {
    return removeStorageItem(storage, key, options);
  }
  return writeStorageJson(storage, key, {
    version: FILE_SESSION_STORAGE_VERSION,
    files: normalizedFiles
  }, options);
}

function updateIndex(storage, namespace, fileKey, options = {}) {
  const normalizedFileKey = normalizeString(fileKey);
  if (!normalizedFileKey) {
    return true;
  }
  const files = readIndex(storage, namespace);
  return files.includes(normalizedFileKey)
    ? true
    : writeIndex(storage, namespace, [...files, normalizedFileKey], options);
}

function entryUrdfSignature(entry) {
  return entryUrdfAssetHash(entry);
}

function entryDxfSignature(entry) {
  return entryAssetHash(entry, "dxf");
}

function entryStepModuleSignature(entry) {
  return [
    entryAssetHash(entry, "stepModule"),
    normalizeString(entry?.hash)
  ].filter(Boolean).join(":");
}

function entryImplicitSignature(entry) {
  return [
    entryAssetHash(entry, "implicit"),
    normalizeString(entry?.hash)
  ].filter(Boolean).join(":");
}

function entryLargeFileSignature(entry) {
  return [
    normalizeString(entry?.kind).toLowerCase(),
    normalizeString(entry?.hash),
    entryAssetHash(entry, "selectorTopology"),
    entryAssetHash(entry, "topology"),
    entryAssetHash(entry, "glb")
  ].filter(Boolean).join(":") || normalizeString(entry?.file);
}

function entryTabSignature(entry) {
  const kind = normalizeString(entry?.kind).toLowerCase();
  return [
    kind,
    normalizeString(entry?.hash),
    entryAssetHash(entry, "selectorTopology"),
    entryAssetHash(entry, "topology"),
    entryAssetHash(entry, "glb"),
    entryAssetHash(entry, "stl"),
    entryAssetHash(entry, "3mf"),
    entryAssetHash(entry, "dxf"),
    entryUrdfSignature(entry)
  ].filter(Boolean).join(":") || normalizeString(entry?.file);
}

export function fileSessionSignaturesForEntry(entry) {
  return {
    tab: entryTabSignature(entry),
    dxf: entryDxfSignature(entry),
    stepModule: entryStepModuleSignature(entry),
    implicit: entryImplicitSignature(entry),
    urdf: entryUrdfSignature(entry),
    largeFile: entryLargeFileSignature(entry)
  };
}

function normalizeDisplaySlice(value) {
  if (!isPlainObject(value)) {
    return null;
  }
  return normalizeDisplaySettings(value);
}

function normalizeDxfBendSettings(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((setting) => {
      if (!isPlainObject(setting)) {
        return null;
      }
      const direction = normalizeString(setting.direction).toLowerCase() === "down" ? "down" : "up";
      return {
        id: normalizeString(setting.id),
        direction,
        angleDeg: Math.min(Math.max(normalizeNumber(setting.angleDeg, 0), 0), 180)
      };
    })
    .filter(Boolean);
}

function normalizeDxfSlice(value) {
  if (!isPlainObject(value)) {
    return null;
  }
  return {
    thicknessMm: normalizePositiveNumber(value.thicknessMm, 0),
    bendSettings: normalizeDxfBendSettings(value.bendSettings)
  };
}

function normalizeStepModuleAnimationState(value) {
  if (!isPlainObject(value)) {
    return {
      activeId: "",
      playing: false,
      elapsedSec: 0,
      speed: 1
    };
  }
  return {
    activeId: normalizeString(value.activeId),
    playing: false,
    elapsedSec: Math.max(normalizeNumber(value.elapsedSec, 0), 0),
    speed: Math.min(Math.max(normalizeNumber(value.speed, 1), 0.1), 5)
  };
}

function normalizeStepModuleSlice(value) {
  if (!isPlainObject(value)) {
    return null;
  }
  return {
    enabled: normalizeBoolean(value.enabled, true),
    parameterValues: isPlainObject(value.parameterValues) ? cloneSerializable(value.parameterValues) : {},
    animationState: normalizeStepModuleAnimationState(value.animationState)
  };
}

function normalizeImplicitSlice(value) {
  if (!isPlainObject(value)) {
    return null;
  }
  return {
    parameterValues: isPlainObject(value.parameterValues) ? cloneSerializable(value.parameterValues) : {},
    animationState: normalizeStepModuleAnimationState(value.animationState)
  };
}

function normalizeJointValues(value) {
  if (!isPlainObject(value)) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value)
      .map(([name, jointValue]) => [normalizeString(name), normalizeNumber(jointValue, 0)])
      .filter(([name]) => name)
  );
}

function normalizeMotionTargets(value) {
  if (!isPlainObject(value)) {
    return {};
  }
  const targets = {};
  for (const [name, target] of Object.entries(value)) {
    const normalizedName = normalizeString(name);
    if (!normalizedName || !Array.isArray(target)) {
      continue;
    }
    targets[normalizedName] = [
      normalizeNumber(target[0], 0),
      normalizeNumber(target[1], 0),
      normalizeNumber(target[2], 0)
    ];
  }
  return targets;
}

function normalizeUrdfMotionState(value) {
  if (!isPlainObject(value)) {
    return {};
  }
  const state = {};
  for (const key of [
    "activePlanningGroupName",
    "activeEndEffectorName",
    "targetFrame",
    "planningPipeline",
    "plannerId"
  ]) {
    const normalized = normalizeString(value[key]);
    if (normalized) {
      state[key] = normalized;
    }
  }
  for (const key of [
    "ikTimeout",
    "ikAttempts",
    "ikTolerance",
    "planningTime",
    "maxVelocityScalingFactor",
    "maxAccelerationScalingFactor"
  ]) {
    if (hasOwn(value, key)) {
      state[key] = normalizeNumber(value[key], 0);
    }
  }
  const targetsByEndEffector = normalizeMotionTargets(value.targetsByEndEffector);
  if (Object.keys(targetsByEndEffector).length) {
    state.targetsByEndEffector = targetsByEndEffector;
  }
  return state;
}

function normalizeUrdfSlice(value) {
  if (!isPlainObject(value)) {
    return null;
  }
  return {
    jointValues: normalizeJointValues(value.jointValues),
    motionState: normalizeUrdfMotionState(value.motionState)
  };
}

function normalizeLargeFileSlice(value) {
  if (!isPlainObject(value)) {
    return null;
  }
  return {
    selectableTopologyEnabled: normalizeBoolean(value.selectableTopologyEnabled, false)
  };
}

const FILE_SESSION_SLICE_SCHEMA = Object.freeze({
  display: {
    normalize: normalizeDisplaySlice,
    equals: displaySettingsEqual,
    signatureKey: "tab"
  },
  tab: {
    normalize: cloneTabSnapshot,
    equals: tabSnapshotEqual,
    signatureKey: "tab"
  },
  dxf: {
    normalize: normalizeDxfSlice,
    equals: storageValuesEqual,
    signatureKey: "dxf"
  },
  stepModule: {
    normalize: normalizeStepModuleSlice,
    equals: storageValuesEqual,
    signatureKey: "stepModule"
  },
  implicit: {
    normalize: normalizeImplicitSlice,
    equals: storageValuesEqual,
    signatureKey: "implicit"
  },
  urdf: {
    normalize: normalizeUrdfSlice,
    equals: storageValuesEqual,
    signatureKey: "urdf"
  },
  largeFile: {
    normalize: normalizeLargeFileSlice,
    equals: storageValuesEqual,
    signatureKey: "largeFile"
  }
});

function sliceSignatureMatches(sliceName, signatures, currentSignatures, options = {}) {
  const signatureKey = FILE_SESSION_SLICE_SCHEMA[sliceName]?.signatureKey;
  if (!signatureKey || options.skipSignatureCheck === true) {
    return true;
  }
  const storedSignature = normalizeString(signatures?.[signatureKey]);
  const currentSignature = normalizeString(currentSignatures?.[signatureKey]);
  return Boolean(storedSignature && currentSignature && storedSignature === currentSignature);
}

function normalizeFileSessionSlices(rawSlices, options = {}) {
  if (!isPlainObject(rawSlices)) {
    return {};
  }
  const currentSignatures = options.currentSignatures || {};
  const signatures = options.signatures || {};
  const slices = {};
  for (const [sliceName, sliceSchema] of Object.entries(FILE_SESSION_SLICE_SCHEMA)) {
    if (!hasOwn(rawSlices, sliceName)) {
      continue;
    }
    if (!sliceSignatureMatches(sliceName, signatures, currentSignatures, options)) {
      continue;
    }
    const normalizedValue = sliceSchema.normalize(rawSlices[sliceName]);
    if (normalizedValue !== null) {
      slices[sliceName] = normalizedValue;
    }
  }
  return slices;
}

export function createFileSessionSnapshot({ fileKey = "", entry = null, slices = {} } = {}) {
  const normalizedFileKey = normalizeString(fileKey || entry?.file);
  return normalizeFileSessionState({
    version: FILE_SESSION_STORAGE_VERSION,
    fileKey: normalizedFileKey,
    signatures: fileSessionSignaturesForEntry(entry),
    slices
  }, {
    fileKey: normalizedFileKey,
    entry,
    skipSignatureCheck: true
  });
}

export function normalizeFileSessionState(rawValue, options = {}) {
  if (!isPlainObject(rawValue) || rawValue.version !== FILE_SESSION_STORAGE_VERSION) {
    return null;
  }
  const normalizedFileKey = normalizeString(rawValue.fileKey || options.fileKey);
  if (!normalizedFileKey || (options.fileKey && normalizedFileKey !== normalizeString(options.fileKey))) {
    return null;
  }
  const signatures = isPlainObject(rawValue.signatures) ? rawValue.signatures : {};
  const currentSignatures = options.entry
    ? fileSessionSignaturesForEntry(options.entry)
    : (options.currentSignatures || signatures);
  const slices = normalizeFileSessionSlices(rawValue.slices, {
    currentSignatures,
    signatures,
    skipSignatureCheck: options.skipSignatureCheck
  });
  return {
    version: FILE_SESSION_STORAGE_VERSION,
    fileKey: normalizedFileKey,
    signatures: { ...signatures },
    slices
  };
}

export function readFileSessionState(namespace, fileKey, entry = null, options = {}) {
  const storage = options.storage || browserSessionStorage();
  const normalizedFileKey = normalizeString(fileKey || entry?.file);
  if (!storage || !normalizedFileKey) {
    return null;
  }
  return normalizeFileSessionState(
    readStorageJson(storage, fileSessionStorageKey(namespace, normalizedFileKey)),
    {
      fileKey: normalizedFileKey,
      entry
    }
  );
}

export function writeFileSessionState(namespace, fileKey, snapshot, options = {}) {
  const storage = options.storage || browserSessionStorage();
  const normalizedFileKey = normalizeString(fileKey || snapshot?.fileKey);
  if (!storage || !normalizedFileKey) {
    return true;
  }
  const normalizedSnapshot = normalizeFileSessionState(snapshot, {
    fileKey: normalizedFileKey,
    skipSignatureCheck: true
  });
  const key = fileSessionStorageKey(namespace, normalizedFileKey);
  if (!normalizedSnapshot || !Object.keys(normalizedSnapshot.slices).length) {
    return removeStorageItem(storage, key, options);
  }
  const wroteSnapshot = writeStorageJson(storage, key, normalizedSnapshot, options);
  const updatedIndex = updateIndex(storage, namespace, normalizedFileKey, options);
  return wroteSnapshot && updatedIndex;
}

export function pruneFileSessionState(namespace, knownFileKeys, options = {}) {
  const storage = options.storage || browserSessionStorage();
  if (!storage) {
    return true;
  }
  const knownFiles = new Set(
    (Array.isArray(knownFileKeys) ? knownFileKeys : []).map((file) => normalizeString(file)).filter(Boolean)
  );
  const files = readIndex(storage, namespace);
  let ok = true;
  const keptFiles = [];
  for (const file of files) {
    if (knownFiles.has(file)) {
      keptFiles.push(file);
      continue;
    }
    ok = removeStorageItem(storage, fileSessionStorageKey(namespace, file), options) && ok;
  }
  return writeIndex(storage, namespace, keptFiles, options) && ok;
}

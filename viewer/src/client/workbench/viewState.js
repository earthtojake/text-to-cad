export const CAD_EXPLORER_VIEW_STATE_SCHEMA = "cad-explorer-view-state";
export const CAD_EXPLORER_VIEW_STATE_VERSION = 1;
export const CAD_REVIEW_STATE_SCHEMA = "cad-review-state";
export const CAD_REVIEW_STATE_VERSION = 1;

/**
 * Clipboard-safe snapshot of the CAD Explorer context needed to reproduce a reviewed view.
 *
 * @typedef {Object} CadExplorerViewState
 * @property {"cad-explorer-view-state"} schema
 * @property {number} version
 * @property {string} createdAt
 * @property {{key: string, cadPath: string, renderFormat: string, entry: Object|null}} file
 * @property {{perspective: Object|null}} camera
 * @property {{
 *   selectedPartIds: string[],
 *   selectedParts: Object[],
 *   selectedReferenceIds: string[],
 *   selectedReferences: Object[],
 *   cadRefs: string[]
 * }} selection
 * @property {{partId: string, referenceId: string}} hover
 * @property {{hiddenPartIds: string[], expandedTreeNodeIds: string[], expandedAssemblyPartIds: string[]}} assembly
 * @property {{clipSettings: Object|null, themeSettings: Object|null, layout: Object|null}} view
 * @property {{url: string}} browser
 * @property {string} notes
 */

function normalizeString(value) {
  return String(value || "").trim();
}

function uniqueStrings(values) {
  const seen = new Set();
  const result = [];
  for (const value of Array.isArray(values) ? values : []) {
    const normalized = normalizeString(value);
    if (!normalized || seen.has(normalized)) {
      continue;
    }
    seen.add(normalized);
    result.push(normalized);
  }
  return result;
}

function cloneJson(value) {
  if (value === null || typeof value === "undefined") {
    return null;
  }
  try {
    return JSON.parse(JSON.stringify(value));
  } catch {
    return null;
  }
}

function cloneObject(value) {
  const cloned = cloneJson(value);
  return cloned && typeof cloned === "object" && !Array.isArray(cloned) ? cloned : {};
}

function normalizeStringMap(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const result = {};
  for (const [key, childValue] of Object.entries(source)) {
    const normalizedKey = normalizeString(key);
    const normalizedValue = normalizeString(childValue);
    if (normalizedKey && normalizedValue) {
      result[normalizedKey] = normalizedValue;
    }
  }
  return result;
}

function encodeBase64Url(text) {
  if (typeof Buffer !== "undefined") {
    return Buffer.from(String(text), "utf8").toString("base64url");
  }
  const bytes = new TextEncoder().encode(String(text));
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function decodeBase64Url(value) {
  const normalized = String(value || "").replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), "=");
  if (typeof Buffer !== "undefined") {
    return Buffer.from(padded, "base64").toString("utf8");
  }
  const binary = atob(padded);
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

function clonePerspective(value) {
  const cloned = cloneObject(value);
  const position = Array.isArray(cloned.position) ? cloned.position.map(Number) : [];
  const target = Array.isArray(cloned.target) ? cloned.target.map(Number) : [];
  const up = Array.isArray(cloned.up) ? cloned.up.map(Number) : [];
  if (
    position.length < 3 ||
    target.length < 3 ||
    up.length < 3 ||
    ![...position.slice(0, 3), ...target.slice(0, 3), ...up.slice(0, 3)].every(Number.isFinite)
  ) {
    return null;
  }
  return {
    ...cloned,
    position: position.slice(0, 3),
    target: target.slice(0, 3),
    up: up.slice(0, 3)
  };
}

/**
 * Normalize a POSIX-style path, resolving "." and ".." segments.
 * Backslashes are treated as separators.
 */
export function normalizePosixPath(path) {
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

function entrySummary(entry) {
  if (!entry) {
    return null;
  }
  return {
    key: normalizeString(entry.key),
    kind: normalizeString(entry.kind),
    name: normalizeString(entry.name),
    file: normalizeString(entry.file),
    path: normalizeString(entry.path),
    cadPath: normalizeString(entry.cadPath),
    sourcePath: normalizeString(entry.source?.path || entry.sourcePath),
    stepPath: normalizeString(entry.step?.path || entry.stepPath)
  };
}

function partSummary(part) {
  return {
    id: normalizeString(part?.id),
    occurrenceId: normalizeString(part?.occurrenceId),
    name: normalizeString(part?.name || part?.displayName || part?.label),
    displayName: normalizeString(part?.displayName || part?.name || part?.label),
    nodeType: normalizeString(part?.nodeType),
    sourceKind: normalizeString(part?.sourceKind),
    sourcePath: normalizeString(part?.sourcePath || part?.partSourcePath),
    instancePath: normalizeString(part?.instancePath),
    leafPartIds: uniqueStrings(part?.leafPartIds)
  };
}

function referenceSummary(reference) {
  return {
    id: normalizeString(reference?.id),
    copyText: normalizeString(reference?.copyText),
    cadRef: normalizeString(reference?.cadRef),
    displaySelector: normalizeString(reference?.displaySelector),
    normalizedSelector: normalizeString(reference?.normalizedSelector),
    selectorType: normalizeString(reference?.selectorType),
    entityType: normalizeString(reference?.entityType),
    partId: normalizeString(reference?.partId),
    occurrenceId: normalizeString(reference?.occurrenceId),
    summary: normalizeString(reference?.summary)
  };
}

/**
 * Build a normalized, versioned view-state document for clipboard sharing.
 *
 * @returns {CadExplorerViewState}
 */
export function buildCadViewState({
  version = CAD_EXPLORER_VIEW_STATE_VERSION,
  createdAt = new Date().toISOString(),
  entry = null,
  cadPath = "",
  renderFormat = "",
  perspective = null,
  selectedPartIds = [],
  selectedParts = [],
  selectedReferenceIds = [],
  selectedReferences = [],
  selectedCadRefs = [],
  hoveredPartId = "",
  hoveredReferenceId = "",
  hiddenPartIds = [],
  expandedTreeNodeIds = [],
  expandedAssemblyPartIds = [],
  selectedRenderPartIdByAssemblyPartId = {},
  explorerMode = "",
  clipSettings = null,
  themeSettings = null,
  layout = null,
  url = "",
  notes = ""
} = {}) {
  const normalizedCadPath = normalizeString(cadPath);
  const entryData = entrySummary(entry);
  return {
    schema: CAD_EXPLORER_VIEW_STATE_SCHEMA,
    version,
    createdAt,
    file: {
      key: entryData?.key || "",
      cadPath: normalizedCadPath,
      renderFormat: normalizeString(renderFormat),
      entry: entryData
    },
    camera: {
      perspective: clonePerspective(perspective)
    },
    selection: {
      selectedPartIds: uniqueStrings(selectedPartIds),
      selectedParts: (Array.isArray(selectedParts) ? selectedParts : []).map(partSummary).filter((part) => part.id),
      selectedReferenceIds: uniqueStrings(selectedReferenceIds),
      selectedReferences: (Array.isArray(selectedReferences) ? selectedReferences : []).map(referenceSummary).filter((reference) => reference.id),
      cadRefs: uniqueStrings(selectedCadRefs)
    },
    hover: {
      partId: normalizeString(hoveredPartId),
      referenceId: normalizeString(hoveredReferenceId)
    },
    assembly: {
      hiddenPartIds: uniqueStrings(hiddenPartIds),
      expandedTreeNodeIds: uniqueStrings(expandedTreeNodeIds),
      expandedAssemblyPartIds: uniqueStrings(expandedAssemblyPartIds)
    },
    scene: {
      explorerMode: normalizeString(explorerMode),
      selectedRenderPartIdByAssemblyPartId: normalizeStringMap(selectedRenderPartIdByAssemblyPartId)
    },
    view: {
      clipSettings: cloneJson(clipSettings),
      themeSettings: cloneJson(themeSettings),
      layout: cloneJson(layout)
    },
    browser: {
      url: normalizeString(url)
    },
    notes: normalizeString(notes)
  };
}

export function formatCadViewStateForClipboard(viewState) {
  const state = cloneObject(viewState);
  const file = state.file || {};
  const selection = state.selection || {};
  const summary = [
    "CAD Explorer view state",
    file.cadPath ? `File: ${file.cadPath}` : "",
    selection.selectedPartIds?.length ? `Parts: ${selection.selectedPartIds.join(", ")}` : "",
    selection.cadRefs?.length ? `CAD refs: ${selection.cadRefs.join(", ")}` : "",
  ].filter(Boolean);
  return `${summary.join("\n")}\n\n${JSON.stringify(state, null, 2)}\n`;
}

function tryParseViewStateJson(text, startIndex, endIndex) {
  try {
    const value = JSON.parse(text.slice(startIndex, endIndex + 1));
    return value && typeof value === "object" && !Array.isArray(value) ? value : null;
  } catch {
    return null;
  }
}

export function parseCadViewStateClipboardText(text) {
  const clipboardText = String(text || "").trim();
  if (!clipboardText) {
    throw new Error("Clipboard is empty");
  }

  const direct = tryParseViewStateJson(clipboardText, 0, clipboardText.length - 1);
  if (direct?.schema === CAD_EXPLORER_VIEW_STATE_SCHEMA) {
    return direct;
  }

  const firstBraceIndex = clipboardText.indexOf("{");
  if (firstBraceIndex < 0) {
    throw new Error("Clipboard does not contain CAD view state JSON");
  }

  for (let endIndex = clipboardText.lastIndexOf("}"); endIndex > firstBraceIndex; endIndex = clipboardText.lastIndexOf("}", endIndex - 1)) {
    const parsed = tryParseViewStateJson(clipboardText, firstBraceIndex, endIndex);
    if (parsed?.schema === CAD_EXPLORER_VIEW_STATE_SCHEMA) {
      return parsed;
    }
  }

  throw new Error("Clipboard does not contain a valid CAD view state");
}

// ── URL query param helpers ────────────────────────────────────────────────

export const CAD_VIEW_STATE_PARAM = "view";
export const CAD_VIEW_CAMERA_PARAM = "v";
export const CAD_VIEW_REFS_PARAM = "sr";
export const CAD_VIEW_PARTS_PARAM = "sp";
export const CAD_VIEW_HIDDEN_PARAM = "hp";
export const CAD_VIEW_CLIP_PARAM = "cp";

const VIEW_STATE_QUERY_PARAMS = [
  CAD_VIEW_STATE_PARAM,
  CAD_VIEW_CAMERA_PARAM,
  CAD_VIEW_REFS_PARAM,
  CAD_VIEW_PARTS_PARAM,
  CAD_VIEW_HIDDEN_PARAM,
  CAD_VIEW_CLIP_PARAM
];

export function hasCadViewStateParams(params) {
  return VIEW_STATE_QUERY_PARAMS.some((name) => params.has(name));
}

function splitCommaList(value) {
  return String(value || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function serializeCameraParam(camera) {
  const p = camera?.perspective || camera;
  if (
    !p ||
    !Array.isArray(p.position) ||
    p.position.length < 3 ||
    !Array.isArray(p.target) ||
    p.target.length < 3 ||
    !Array.isArray(p.up) ||
    p.up.length < 3
  ) {
    return null;
  }
  return [
    ...p.position.slice(0, 3),
    ...p.target.slice(0, 3),
    ...p.up.slice(0, 3)
  ]
    .map((f) => Number(f))
    .join(",");
}

function parseCameraParam(value) {
  const parts = splitCommaList(value).map(Number);
  if (parts.length !== 9 || !parts.every(Number.isFinite)) {
    return null;
  }
  return {
    position: parts.slice(0, 3),
    target: parts.slice(3, 6),
    up: parts.slice(6, 9)
  };
}

function parseClipParam(value) {
  if (!value) {
    return null;
  }
  const parts = splitCommaList(value);
  const axis = parts[0] || "z";
  const plane = parseFloat(parts[1]);
  return {
    axis,
    plane: Number.isFinite(plane) ? plane : 0,
    enabled: true
  };
}

function buildCadReviewStatePayload(viewState) {
  const normalized = normalizeCadViewStateForApply(viewState);
  return {
    schema: CAD_REVIEW_STATE_SCHEMA,
    version: CAD_REVIEW_STATE_VERSION,
    file: {
      key: normalized.file.key,
      cadPath: normalized.file.cadPath,
      renderFormat: normalized.file.renderFormat
    },
    camera: {
      perspective: normalized.camera.perspective
    },
    scene: {
      selectedRenderPartIdByAssemblyPartId: normalized.scene.selectedRenderPartIdByAssemblyPartId
    },
    selection: {
      selectedPartIds: normalized.selection.selectedPartIds,
      selectedReferenceIds: normalized.selection.selectedReferenceIds,
      cadRefs: normalized.selection.cadRefs
    },
    visibility: {
      hiddenPartIds: normalized.assembly.hiddenPartIds
    },
    clip: cloneJson(normalized.view.clipSettings),
    assembly: {
      expandedAssemblyPartIds: normalized.assembly.expandedAssemblyPartIds
    }
  };
}

function buildCadViewStateFromReviewState(reviewState) {
  return buildCadViewState({
    entry: {
      key: reviewState.file?.key,
      file: reviewState.file?.key,
      cadPath: reviewState.file?.cadPath
    },
    cadPath: reviewState.file?.cadPath,
    renderFormat: reviewState.file?.renderFormat,
    perspective: reviewState.camera?.perspective,
    explorerMode: reviewState.scene?.explorerMode,
    selectedRenderPartIdByAssemblyPartId: reviewState.scene?.selectedRenderPartIdByAssemblyPartId,
    selectedPartIds: reviewState.selection?.selectedPartIds,
    selectedReferenceIds: reviewState.selection?.selectedReferenceIds,
    selectedCadRefs: reviewState.selection?.cadRefs,
    hiddenPartIds: reviewState.visibility?.hiddenPartIds,
    expandedAssemblyPartIds: reviewState.assembly?.expandedAssemblyPartIds,
    clipSettings: reviewState.clip
  });
}

/**
 * Build a compact URL query string from review-state data.
 *
 * Does NOT include file identity — the caller is expected to merge with the
 * existing `?file=` param.
 *
 * @param {CadExplorerViewState} viewState
 * @returns {string}
 */
export function buildCadViewStateQueryString(viewState) {
  const params = new URLSearchParams();
  params.set(CAD_VIEW_STATE_PARAM, encodeBase64Url(JSON.stringify(buildCadReviewStatePayload(viewState))));
  return params.toString();
}

/**
 * Parse view state from URLSearchParams and return a minimal
 * {@link CadExplorerViewState} suitable for `normalizeCadViewStateForApply`.
 *
 * @param {URLSearchParams} params
 * @param {{cadPath?: string}} [options]
 * @returns {CadExplorerViewState|null}
 */
export function buildCadViewStateFromParams(params, { cadPath = "" } = {}) {
  const encodedViewState = params.get(CAD_VIEW_STATE_PARAM);
  if (encodedViewState) {
    try {
      const parsed = JSON.parse(decodeBase64Url(encodedViewState));
      if (parsed?.schema === CAD_REVIEW_STATE_SCHEMA) {
        return buildCadViewStateFromReviewState(parsed);
      }
      if (parsed?.schema === CAD_EXPLORER_VIEW_STATE_SCHEMA) {
        return parsed;
      }
      throw new Error("Unsupported CAD review state URL schema");
    } catch {
      throw new Error("Invalid CAD review state URL");
    }
  }

  if (!hasCadViewStateParams(params)) {
    return null;
  }
  return buildCadViewState({
    cadPath,
    perspective: parseCameraParam(params.get(CAD_VIEW_CAMERA_PARAM)),
    selectedReferenceIds: splitCommaList(params.get(CAD_VIEW_REFS_PARAM)),
    selectedPartIds: splitCommaList(params.get(CAD_VIEW_PARTS_PARAM)),
    hiddenPartIds: splitCommaList(params.get(CAD_VIEW_HIDDEN_PARAM)),
    clipSettings: parseClipParam(params.get(CAD_VIEW_CLIP_PARAM))
  });
}

export function normalizeCadViewStateForApply(viewState) {
  if (!viewState || typeof viewState !== "object" || viewState.schema !== CAD_EXPLORER_VIEW_STATE_SCHEMA) {
    throw new Error("Unsupported CAD view state");
  }

  return {
    file: {
      key: normalizeString(viewState.file?.key),
      cadPath: normalizeString(viewState.file?.cadPath),
      renderFormat: normalizeString(viewState.file?.renderFormat),
      entry: entrySummary(viewState.file?.entry)
    },
    camera: {
      perspective: clonePerspective(viewState.camera?.perspective)
    },
    selection: {
      selectedPartIds: uniqueStrings(viewState.selection?.selectedPartIds),
      selectedReferenceIds: uniqueStrings(viewState.selection?.selectedReferenceIds),
      cadRefs: uniqueStrings(viewState.selection?.cadRefs)
    },
    assembly: {
      hiddenPartIds: uniqueStrings(viewState.assembly?.hiddenPartIds),
      expandedTreeNodeIds: uniqueStrings(viewState.assembly?.expandedTreeNodeIds),
      expandedAssemblyPartIds: uniqueStrings(viewState.assembly?.expandedAssemblyPartIds)
    },
    scene: {
      explorerMode: normalizeString(viewState.scene?.explorerMode),
      selectedRenderPartIdByAssemblyPartId: normalizeStringMap(viewState.scene?.selectedRenderPartIdByAssemblyPartId)
    },
    view: {
      clipSettings: cloneJson(viewState.view?.clipSettings),
      themeSettings: cloneJson(viewState.view?.themeSettings),
      layout: cloneJson(viewState.view?.layout)
    }
  };
}

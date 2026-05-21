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

export function buildCadViewState({
  version = 1,
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
  clipSettings = null,
  themeSettings = null,
  layout = null,
  url = "",
  notes = ""
} = {}) {
  const normalizedCadPath = normalizeString(cadPath);
  const entryData = entrySummary(entry);
  return {
    schema: "cad-explorer-view-state",
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

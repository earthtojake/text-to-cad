import { buildCadRefToken, parseCadRefSelector, parseCadRefToken, sortCadRefSelectors } from "cadjs/lib/cadRefs.js";
import { entryReferenceAssetSignature } from "cadjs/lib/entryAssets.js";
import { buildSelectorRuntime } from "cadjs/lib/selectors/runtime.js";
import { cadPathForEntry, fileKey } from "./sidebar.js";

const ASSEMBLY_MATE_SELECTOR_RE = /^m\d+$/;

export function buildReferenceCacheKey(entry) {
  const fileRef = fileKey(entry);
  const referenceHash = entryReferenceAssetSignature(entry);
  return fileRef && referenceHash ? `${fileRef}:${referenceHash}` : "";
}

export function normalizeReferenceList(value) {
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

export function buildNormalizedReferenceState(entry, referencePayload = null, {
  copyCadPath,
  partId = "",
  transform = null,
  remapOccurrenceId = "",
  remapOccurrencePrefix = null
} = {}) {
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
    stepRelPath: fileKey(entry),
    stepHash: String(selectorRuntime.stepHash || entry?.hash || ""),
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

export function parseAssemblyPartReferenceSelectionId(referenceId) {
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
  void cadPath;
  const groupKind = String(selector || "").trim() || "root";
  return `selector-ref::${groupKind}`;
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

export function canonicalCadRefCopyText(text, { allowPlain = false } = {}) {
  const normalizedText = String(text || "").trim();
  if (!normalizedText) {
    return "";
  }
  if (!normalizedText.startsWith("#")) {
    return allowPlain ? normalizedText : "";
  }
  const token = normalizedText.split(/\s+/)[0];
  return token || "";
}

export function copySelectedReferenceText(references) {
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
    .map((line) => canonicalCadRefCopyText(line, { allowPlain: true }))
    .filter(Boolean);

  return {
    text: lines.join("\n")
  };
}

export function buildAssemblyPartCopyText(part, entry) {
  void entry;

  const selector = [
    part?.displaySelector,
    part?.occurrenceId,
    part?.sourceOccurrenceId,
    part?.sourceRootTargetOccurrenceId,
    part?.id
  ].map((value) => {
    const candidate = String(value || "").trim();
    return /^(?:o\d+(?:\.\d+)*(?:\.[sfev]\d+)?|[sfev]\d+|m\d+)$/i.test(candidate)
      ? candidate
      : "";
  }).find(Boolean) || "";
  if (!selector) {
    return "";
  }
  return buildCadRefToken({
    selector
  });
}

export function buildWholeStepEntryCopyReference(entry) {
  if (!entry) {
    return null;
  }
  return {
    id: "step-entry:whole",
    copyText: buildCadRefToken()
  };
}

export function buildAssemblyMateSelector(mate) {
  return String(mate?.id || "").trim();
}

export function parseAssemblyMateSelector(selector) {
  const normalizedSelector = String(selector || "").trim();
  return ASSEMBLY_MATE_SELECTOR_RE.test(normalizedSelector) ? normalizedSelector : "";
}

export function buildAssemblyMateCopyText(mate, entry) {
  void entry;
  const selector = buildAssemblyMateSelector(mate);
  if (!selector) {
    return "";
  }
  return buildCadRefToken({ selector });
}

export function buildAssemblyMateSelectorMap(mates) {
  const map = new Map();
  for (const mate of Array.isArray(mates) ? mates : []) {
    const mateId = String(mate?.id || "").trim();
    if (!mateId) {
      continue;
    }
    const selector = buildAssemblyMateSelector(mate);
    if (selector) {
      map.set(selector, mateId);
    }
  }
  return map;
}

export function buildSelectionCopyPayload({ references = [], parts = [], mates = [], entry = null } = {}) {
  const referencesForCopy = Array.isArray(references) ? [...references] : [];
  const missingPartNames = [];

  for (const part of parts) {
    const copyText = buildAssemblyPartCopyText(part, entry);
    if (!copyText) {
      missingPartNames.push(String(part?.name || part?.id || "part"));
      continue;
    }
    const partReferenceId = String(part?.id || part?.occurrenceId || "").trim();
    referencesForCopy.push({
      id: `assembly-part:${partReferenceId}`,
      copyText
    });
  }

  for (const mate of Array.isArray(mates) ? mates : []) {
    const copyText = buildAssemblyMateCopyText(mate, entry);
    if (!copyText) {
      continue;
    }
    referencesForCopy.push({
      id: `assembly-mate:${String(mate?.id || "").trim()}`,
      copyText
    });
  }

  const { text: referenceText } = copySelectedReferenceText(referencesForCopy);
  const lines = String(referenceText || "")
    .split("\n")
    .map((line) => canonicalCadRefCopyText(line, { allowPlain: true }))
    .filter(Boolean);

  return {
    lines,
    copiedCount: referencesForCopy.length,
    missingPartNames
  };
}

export function buildSelectionCopyButtonLabel(lines, { limit = 1 } = {}) {
  const copyLines = Array.isArray(lines) ? lines : [];
  const normalizedLimit = Math.max(1, Number(limit) || 1);
  const tokens = copyLines
    .map((line) => canonicalCadRefCopyText(line, { allowPlain: true }))
    .filter(Boolean);

  if (!tokens.length) {
    return "Copy refs";
  }

  const visibleTokens = tokens.slice(0, normalizedLimit);
  return `Copy ${visibleTokens.join(", ")}`;
}

export function orderedStringListEqual(a, b) {
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

export function uniqueStringList(values) {
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

export function resolveTopologyRelativeFile(entry, sourcePath) {
  const relativeSourcePath = String(sourcePath || "").trim();
  const stepPath = fileKey(entry);
  if (!relativeSourcePath || !stepPath) {
    return "";
  }
  const stepParts = stepPath.split("/");
  const stepFilename = stepParts.pop();
  const stepDirectory = stepParts.join("/");
  const topologyDirectory = stepDirectory ? `${stepDirectory}/.${stepFilename}` : `.${stepFilename}`;
  return normalizePosixPath(`${topologyDirectory}/${relativeSourcePath}`);
}

export function cadRefQueryHasKnownEntry(cadRefs, entries) {
  void cadRefs;
  void entries;
  return false;
}

export function collectCadRefSelectionRequest(cadRefs, entry) {
  const selectors = [];
  let hasMatchingToken = false;
  let hasWholeEntryToken = false;

  if (!entry) {
    return {
      hasMatchingToken,
      hasWholeEntryToken,
      selectors,
      needsParts: false,
      needsMates: false,
      needsReferences: false
    };
  }

  for (const cadRef of Array.isArray(cadRefs) ? cadRefs : []) {
    const parsedToken = parseCadRefToken(cadRef);
    if (!parsedToken) {
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
  let needsMates = false;
  let needsReferences = false;
  for (const selector of normalizedSelectors) {
    const parsedSelector = parseCadRefSelector(selector);
    if (parseAssemblyMateSelector(selector)) {
      needsMates = true;
    } else if (entry?.kind === "assembly" && parsedSelector?.selectorType === "occurrence") {
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
    needsMates,
    needsReferences
  };
}

function addTokenSelectorsToMap(map, copyText, value) {
  const parsedToken = parseCadRefToken(copyText);
  if (!parsedToken) {
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

export function buildReferenceSelectorMap(references, cadPath) {
  void cadPath;
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
    addTokenSelectorsToMap(map, reference?.copyText, value);
    addReferenceIdSelectorToMap(map, reference, value);
  }
  return map;
}

export function buildAssemblyPartSelectorMap(parts, cadPath) {
  void cadPath;
  const map = new Map();
  for (const part of Array.isArray(parts) ? parts : []) {
    const partId = String(part?.id || "").trim();
    const selector = String(part?.occurrenceId || partId).trim();
    const selectionId = partId || selector;
    if (!selectionId || !selector) {
      continue;
    }
    const copyText = buildCadRefToken({
      cadPath,
      selector
    });
    addTokenSelectorsToMap(map, copyText, selectionId);
    addTokenSelectorsToMap(map, selector, selectionId);
  }
  return map;
}

export function resolveCadRefSelection({
  cadRefs = [],
  entry = null,
  references = [],
  assemblyParts = [],
  assemblyMates = [],
  isAssemblyView = false
} = {}) {
  const request = collectCadRefSelectionRequest(cadRefs, entry);
  const cadPath = cadPathForEntry(entry);
  const referenceSelectorMap = buildReferenceSelectorMap(references, cadPath);
  const assemblyPartSelectorMap = buildAssemblyPartSelectorMap(assemblyParts, cadPath);
  const assemblyMateSelectorMap = buildAssemblyMateSelectorMap(assemblyMates);
  const selectedReferenceIds = [];
  const selectedPartIds = [];
  const selectedMateIds = [];
  const expandedAssemblyPartIds = [];

  for (const selector of request.selectors) {
    const parsedSelector = parseCadRefSelector(selector);
    const canonicalSelector = String(parsedSelector?.canonical || selector || "").trim();
    if (!canonicalSelector) {
      continue;
    }

    const mateId = assemblyMateSelectorMap.get(canonicalSelector);
    if (mateId) {
      selectedMateIds.push(mateId);
      continue;
    }

    if (isAssemblyView && parsedSelector?.selectorType === "occurrence") {
      const partId = assemblyPartSelectorMap.get(canonicalSelector);
      if (partId) {
        selectedPartIds.push(partId);
        expandedAssemblyPartIds.push(partId);
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
    selectedMateIds: uniqueStringList(selectedMateIds),
    inspectedAssemblyNodeId: "",
    expandedAssemblyPartIds: uniqueStringList(expandedAssemblyPartIds)
  };
}

export function computeNextSelectionIds(currentIds, selectionId, { multiSelect = false } = {}) {
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

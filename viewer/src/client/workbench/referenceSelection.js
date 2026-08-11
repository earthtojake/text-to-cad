import { buildCadRefToken, parseCadRefToken, sortCadRefSelectors } from "cadjs/lib/cadRefs.js";
import { entryReferenceAssetSignature } from "cadjs/lib/entryAssets.js";
import { buildSelectorRuntime } from "cadjs/lib/selectors/runtime.js";
import { cadPathForEntry, fileKey } from "./sidebar.js";

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
  remapOccurrencePrefix = null,
  selectorRuntime: prebuiltSelectorRuntime = null,
  loadedTopologyKey = ""
} = {}) {
  // A component-GLB package has no whole-assembly selector bundle; the caller composes the
  // per-component runtimes and passes the result here instead of a single bundle to parse.
  const selectorRuntime = prebuiltSelectorRuntime || buildSelectorRuntime(referencePayload, {
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
    loadedTopologyKey,
    disabledReason: ""
  };
}

// Lazy assembly topology: from a component-GLB package descriptor, pick only the occurrences whose
// ids are in `requestedOccurrenceIds` (the tree nodes the user expanded) and the de-duplicated set
// of component cids they need. A single-component part has no assembly tree, so it loads every
// occurrence. `loadedTopologyKey` is a stable key over the requested set so callers can detect when
// the expanded set grows and re-load only the newly-needed components.
export function selectRequestedAssemblyComponents(
  packageDescriptor,
  requestedOccurrenceIds,
  { singleComponentPart = false } = {}
) {
  const occurrences = Array.isArray(packageDescriptor?.occurrences) ? packageDescriptor.occurrences : [];
  const requestedSet = new Set(
    (Array.isArray(requestedOccurrenceIds) ? requestedOccurrenceIds : [])
      .map((id) => String(id || "").trim())
      .filter(Boolean)
  );
  const occurrencesToLoad = singleComponentPart
    ? occurrences
    : occurrences.filter((occurrence) => requestedSet.has(String(occurrence?.id || "").trim()));
  const neededCids = [];
  const seenCids = new Set();
  for (const occurrence of occurrencesToLoad) {
    const cid = String(occurrence?.component || "").trim();
    if (cid && !seenCids.has(cid)) {
      seenCids.add(cid);
      neededCids.push(cid);
    }
  }
  const loadedTopologyKey = singleComponentPart ? "*" : [...requestedSet].sort().join("|");
  return { occurrencesToLoad, neededCids, loadedTopologyKey };
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

export function buildAssemblyMateCopyText(mate, entry) {
  void entry;
  const selector = buildAssemblyMateSelector(mate);
  if (!selector) {
    return "";
  }
  return buildCadRefToken({ selector });
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

import { entryHasMesh } from "@hardcore/core/lib/entryAssets.js";

const STEP_ARTIFACT_GENERATION_FAILURE_DISPLAY_THRESHOLD = 3;

export const BUILDABLE_STEP_ARTIFACT_ERROR_CODES = Object.freeze([
  "missing_glb",
  "missing_step_topology",
  "missing_edge_topology",
  "missing_surface_edge_attributes",
  "missing_selector_topology",
  "unsupported_step_topology"
]);

const BUILDABLE_STEP_ARTIFACT_ERROR_CODE_SET = new Set(BUILDABLE_STEP_ARTIFACT_ERROR_CODES);
const STEP_FILE_EXTENSION_RE = /\.(step|stp)$/i;

function normalizeStepArtifactFileRef(value) {
  return String(value || "").trim().replace(/\\/g, "/").replace(/\/+$/, "");
}

function valuesArray(value) {
  if (!value) {
    return [];
  }
  if (Array.isArray(value)) {
    return value;
  }
  if (typeof value !== "string" && typeof value[Symbol.iterator] === "function") {
    return Array.from(value);
  }
  return [value];
}

function addFileRef(refs, value) {
  const normalized = normalizeStepArtifactFileRef(value);
  if (normalized) {
    refs.add(normalized);
  }
  return normalized;
}

function addStepFileRef(refs, value) {
  const normalized = addFileRef(refs, value);
  if (!STEP_FILE_EXTENSION_RE.test(normalized)) {
    return;
  }
  const slashIndex = normalized.lastIndexOf("/");
  const dir = slashIndex >= 0 ? `${normalized.slice(0, slashIndex)}/` : "";
  const filename = slashIndex >= 0 ? normalized.slice(slashIndex + 1) : normalized;
  refs.add(`${dir}.${filename}.glb`);
}

function fileRefsMatch(left, right) {
  const leftRef = normalizeStepArtifactFileRef(left);
  const rightRef = normalizeStepArtifactFileRef(right);
  return Boolean(leftRef && rightRef && leftRef === rightRef);
}

function fileRefMatchesAny(file, candidates) {
  return candidates.some((candidate) => fileRefsMatch(file, candidate));
}

function stepArtifactGenerationFailureCount(state) {
  const count = Number(state?.failureCount || 0);
  return Number.isFinite(count) && count > 0 ? Math.trunc(count) : 0;
}

function stepArtifactGenerationFileRefs(entry = null, artifact = entry?.artifact) {
  const refs = new Set();
  addStepFileRef(refs, entry?.file);
  addStepFileRef(refs, entry?.rootRelativeFile);
  addStepFileRef(refs, artifact?.stepPath);
  if (STEP_FILE_EXTENSION_RE.test(normalizeStepArtifactFileRef(artifact?.sourcePath))) {
    addStepFileRef(refs, artifact?.sourcePath);
  }
  return [...refs];
}

export function stepArtifactGenerationInProgress({
  entry = null,
  artifact = entry?.artifact,
  generationState = null,
  activeGenerationFiles = []
} = {}) {
  const candidates = stepArtifactGenerationFileRefs(entry, artifact);
  if (String(generationState?.status || "").trim().toLowerCase() === "loading") {
    const stateFile = normalizeStepArtifactFileRef(generationState?.file);
    if (!stateFile || candidates.length === 0 || fileRefMatchesAny(stateFile, candidates)) {
      return true;
    }
  }

  return valuesArray(activeGenerationFiles)
    .map(normalizeStepArtifactFileRef)
    .filter(Boolean)
    .some((file) => fileRefMatchesAny(file, candidates));
}

export function stepArtifactIssueShouldSuppress({
  entry = null,
  artifact = entry?.artifact,
  generationAvailable = true,
  generationState = null,
  activeGenerationFiles = []
} = {}) {
  const candidateEntry = { ...(entry || {}), artifact };
  const generationInProgress = stepArtifactGenerationInProgress({
    entry: candidateEntry,
    artifact,
    generationState,
    activeGenerationFiles
  });
  if (!stepArtifactCanGenerate(
    candidateEntry,
    { generationAvailable: generationAvailable || generationInProgress }
  )) {
    return false;
  }
  if (generationInProgress) {
    return true;
  }
  return stepArtifactGenerationFailureCount(generationState) <
    STEP_ARTIFACT_GENERATION_FAILURE_DISPLAY_THRESHOLD;
}

// The entry's failed STEP artifact record, or null.
//
// These used to take the entry's format and check it was a STEP, because one renderer served
// every format and a DXF - artifact-managed too - would otherwise have been shown a card about
// a STEP artifact. A DXF is its own renderer now and never reaches this module: the STEP
// renderer is only handed STEPs (its `matches`), so there is no format left to ask about.
export function failedStepArtifact(entry) {
  return entry?.artifact?.ok === false ? entry.artifact : null;
}

// A STEP artifact whose metadata is incomplete can still carry a renderable mesh:
// the viewport shows it and the alert drops to a warning instead of an error.
export function stepArtifactHasRenderableGlb(entry) {
  return entryHasMesh(entry);
}

// The alert description for a failed STEP artifact: its error code in words.
export function stepArtifactStatusMessage(artifact) {
  const code = String(artifact?.error || "").trim();
  if (code === "missing_glb") {
    return "Generated GLB is missing.";
  }
  if (code === "missing_step_topology") {
    return "Generated GLB is missing STEP topology metadata.";
  }
  if (code === "missing_selector_topology") {
    return "Generated GLB is missing selector topology metadata.";
  }
  if (code === "missing_edge_topology") {
    return "Generated GLB is missing surface edge topology metadata.";
  }
  if (code === "missing_surface_edge_attributes") {
    return "Generated GLB is missing surface edge render attributes.";
  }
  if (code === "unsupported_step_topology") {
    return "Generated GLB topology metadata is unsupported.";
  }
  if (code === "missing_step_hash") {
    return "Generated GLB is missing the hash of the STEP file.";
  }
  return "Generated STEP artifact is unavailable.";
}

export function stepArtifactCanGenerate(entry, { generationAvailable = true } = {}) {
  if (!generationAvailable) {
    return false;
  }
  if (entry?.artifact?.ok) {
    return false;
  }
  return BUILDABLE_STEP_ARTIFACT_ERROR_CODE_SET.has(String(entry?.artifact?.error || ""));
}

export function stepArtifactNeedsWarning(entry, options = {}) {
  return entry?.artifact?.ok === false && !stepArtifactCanGenerate(entry, options);
}

import { entryHasMesh } from "cadjs/lib/entryAssets.js";
import { RENDER_FORMAT } from "cadjs/lib/fileFormats.js";

const STEP_ARTIFACT_GENERATION_FAILURE_DISPLAY_THRESHOLD = 3;

export const BUILDABLE_STEP_ARTIFACT_ERROR_CODES = Object.freeze([
  "missing_glb",
  "missing_step_topology",
  "missing_edge_topology",
  "missing_surface_edge_attributes",
  "missing_selector_topology",
  "missing_source_path",
  "missing_step_hash",
  "stale_step_artifact",
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
  addFileRef(refs, artifact?.packagePath);
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
  sourceFormat = RENDER_FORMAT.STEP,
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
    sourceFormat,
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
// STEP-shaped on purpose, and NOT `artifactManaged`: DXF is artifact-managed too, but the
// error codes, the `stale` flag and the renderable-GLB fallback below are all STEP package
// vocabulary. Generalising the gate without generalising the vocabulary would show a DXF a
// card about a STEP artifact. The generic "render artifact build failed" card in
// viewerAlerts already covers every artifact-managed kind; this is the STEP detail on top.
export function failedStepArtifact(entry, sourceFormat) {
  return sourceFormat === RENDER_FORMAT.STEP && entry?.artifact?.ok === false
    ? entry.artifact
    : null;
}

export function stepArtifactIsStale(entry, sourceFormat) {
  return (
    sourceFormat === RENDER_FORMAT.STEP &&
    entry?.artifact?.ok === false &&
    (
      entry.artifact.stale === true ||
      String(entry.artifact.error || "") === "stale_step_artifact"
    )
  );
}

export function stepArtifactCanGenerate(entry, sourceFormat, { generationAvailable = true } = {}) {
  if (!generationAvailable || sourceFormat !== RENDER_FORMAT.STEP) {
    return false;
  }
  if (entry?.artifact?.ok) {
    return false;
  }
  return BUILDABLE_STEP_ARTIFACT_ERROR_CODE_SET.has(String(entry?.artifact?.error || ""));
}

export function stepArtifactNeedsWarning(entry, sourceFormat, options = {}) {
  return (
    sourceFormat === RENDER_FORMAT.STEP &&
    entry?.artifact?.ok === false &&
    !stepArtifactCanGenerate(entry, sourceFormat, options)
  );
}

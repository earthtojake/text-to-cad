import { entryHasMesh } from "cadjs/lib/entryAssets.js";
import { RENDER_FORMAT } from "cadjs/lib/fileFormats.js";

export const STEP_ARTIFACT_GENERATION_FAILURE_DISPLAY_THRESHOLD = 3;

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

export function stepArtifactGenerationFailureCount(state) {
  const count = Number(state?.failureCount || 0);
  return Number.isFinite(count) && count > 0 ? Math.trunc(count) : 0;
}

export function stepArtifactGenerationFileRefs(entry = null, artifact = entry?.artifact) {
  const refs = new Set();
  addStepFileRef(refs, entry?.file);
  addStepFileRef(refs, entry?.rootRelativeFile);
  addStepFileRef(refs, artifact?.stepPath);
  if (STEP_FILE_EXTENSION_RE.test(normalizeStepArtifactFileRef(artifact?.sourcePath))) {
    addStepFileRef(refs, artifact?.sourcePath);
  }
  addFileRef(refs, artifact?.glbPath);
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

export function validateGeneratedStepArtifactPayload(payload, { file = "" } = {}) {
  const generatedEntry = payload?.entry;
  if (!generatedEntry) {
    return;
  }
  const fileLabel = String(file || generatedEntry.file || "").trim();
  if (!entryHasMesh(generatedEntry)) {
    throw new Error(`Generated STEP artifact is not renderable: ${fileLabel || "STEP file"}`);
  }
  if (stepArtifactCanGenerate(generatedEntry, RENDER_FORMAT.STEP, { generationAvailable: true })) {
    const code = String(generatedEntry?.artifact?.error || "step_artifact_unavailable").trim();
    throw new Error(`Generated STEP artifact still reports ${code}: ${fileLabel || "STEP file"}`);
  }
}

export async function runStepArtifactGenerationWithRetries({
  key = "",
  file = "",
  initialFailureCount = 0,
  generate,
  isCurrent = () => true,
  onState = () => {},
  onFinalError = () => {},
  threshold = STEP_ARTIFACT_GENERATION_FAILURE_DISPLAY_THRESHOLD,
  validatePayload = null
} = {}) {
  if (typeof generate !== "function") {
    throw new TypeError("STEP artifact generation requires a generate function.");
  }

  const maxFailures = Math.max(1, Math.trunc(Number(threshold) || 0));
  let failureCount = Math.min(
    stepArtifactGenerationFailureCount({ failureCount: initialFailureCount }),
    maxFailures
  );

  while (failureCount < maxFailures) {
    const attempt = failureCount + 1;
    onState({
      key,
      file,
      status: "loading",
      failureCount,
      attempt,
      error: ""
    });

    try {
      const payload = await generate(file, { attempt, failureCount });
      if (!isCurrent()) {
        return { status: "cancelled", failureCount };
      }
      if (typeof validatePayload === "function") {
        validatePayload(payload);
      }
      const readyState = {
        key,
        file,
        status: "ready",
        failureCount: 0,
        error: ""
      };
      onState(readyState);
      return { status: "ready", state: readyState, payload };
    } catch (generationError) {
      if (!isCurrent()) {
        return { status: "cancelled", failureCount };
      }
      failureCount += 1;
      const message = generationError instanceof Error
        ? generationError.message
        : String(generationError);
      const failedState = {
        key,
        file,
        status: failureCount >= maxFailures ? "error" : "loading",
        failureCount,
        attempt: Math.min(failureCount + 1, maxFailures),
        error: message
      };
      onState(failedState);
      if (failedState.status === "error") {
        onFinalError(message, failedState, generationError);
        return { status: "error", state: failedState, error: generationError };
      }
    }
  }

  const exhaustedState = {
    key,
    file,
    status: "error",
    failureCount,
    attempt: maxFailures,
    error: ""
  };
  return { status: "error", state: exhaustedState };
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
